#!/usr/bin/env python3
"""Rebuild current tree as exactly 50 sequential commits."""
from __future__ import annotations

import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET_COMMITS = 50
MAX_RETRIES = 5


def run(*args: str, check: bool = True) -> str:
    for attempt in range(MAX_RETRIES):
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return (result.stdout or "").strip()
        err = (result.stderr or "") + (result.stdout or "")
        if "index.lock" in err and attempt + 1 < MAX_RETRIES:
            lock = ROOT / ".git" / "index.lock"
            if lock.exists():
                try:
                    lock.unlink()
                except OSError:
                    pass
            time.sleep(0.5)
            continue
        print(err, file=sys.stderr)
        if check:
            raise SystemExit(result.returncode)
        return ""
    raise SystemExit(f"Command failed after retries: {' '.join(args)}")


def collect_files() -> list[str]:
    tracked = [line for line in run("git", "ls-files").splitlines() if line]
    untracked = [
        line
        for line in run("git", "ls-files", "--others", "--exclude-standard").splitlines()
        if line and not line.startswith(".venv/")
    ]
    return sorted(set(tracked) | set(untracked))


def sort_key(path: str) -> tuple:
    parts = Path(path).parts
    is_venv = parts and parts[0] == ".venv"
    return (1 if is_venv else 0, path)


def dominant_prefix(files: list[str]) -> str:
    if not files:
        return "repository"
    counts = Counter()
    for path in files:
        parts = Path(path).parts
        if not parts:
            continue
        if parts[0] == ".venv":
            counts[".venv"] += 1
            continue
        key = parts[0] if len(parts) == 1 else f"{parts[0]}/{parts[1]}"
        counts[key] += 1
    return counts.most_common(1)[0][0]


def commit_message(index: int, files: list[str]) -> str:
    prefix = dominant_prefix(files)
    verbs = {
        "backend": "Add backend",
        "renderer": "Add renderer",
        "tests": "Add tests",
        "main.js": "Add Electron",
        "package.json": "Add project",
        ".github": "Add CI",
        "landing": "Add landing",
        "benchmarks": "Add benchmarks",
        "scripts": "Add scripts",
        "preload.js": "Add Electron",
        "adele-docs": "Add docs assets",
        ".venv": "Add Python environment",
    }
    top = prefix.split("/")[0]
    verb = verbs.get(top, f"Add {top}")
    return f"{verb} files ({index + 1}/{TARGET_COMMITS})"


def chunk_evenly(files: list[str], slots: int) -> list[list[str]]:
    if slots <= 0:
        return []
    if not files:
        return [[] for _ in range(slots)]
    groups: list[list[str]] = [[] for _ in range(slots)]
    for index, path in enumerate(files):
        groups[index % slots].append(path)
    return groups


def partition(files: list[str], count: int) -> list[list[str]]:
    source = sorted(f for f in files if not f.startswith(".venv/"))
    venv = sorted(f for f in files if f.startswith(".venv/"))
    source_slots = min(len(source), max(1, count - (1 if venv else 0)))
    venv_slots = count - source_slots
    groups = chunk_evenly(source, source_slots) + chunk_evenly(venv, venv_slots)
    while len(groups) < count:
        groups.append([])
    return groups[:count]


def main() -> None:
    files = collect_files()
    if not files:
        raise SystemExit("No files to commit")

    run("git", "checkout", "--orphan", "split-50-commits")
    run("git", "rm", "-rf", "--cached", ".", check=False)

    groups = partition(files, TARGET_COMMITS)
    for index, group in enumerate(groups):
        if not group:
            run(
                "git", "commit", "--allow-empty",
                "-m", f"Checkpoint ({index + 1}/{TARGET_COMMITS})",
            )
            continue
        for path in group:
            run("git", "add", "--", path)
        run("git", "commit", "-m", commit_message(index, group))
        print(f"Committed {index + 1}/{TARGET_COMMITS}: {len(group)} files")

    run("git", "branch", "-M", "main")
    count = run("git", "rev-list", "--count", "HEAD")
    print(f"Done. main now has {count} commits from {len(files)} files.")


if __name__ == "__main__":
    main()
