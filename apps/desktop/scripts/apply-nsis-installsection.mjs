#!/usr/bin/env node
/**
 * electron-builder always resolves installSection.nsh from app-builder-lib's templates.
 * A custom installer.nsi skips the uninstaller build pass and breaks UNINSTALLER_OUT_FILE.
 * We patch the template copy on each postinstall from build/adele-nsis-installSection.nsh.
 */
import { copyFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const root = process.cwd();
const src = path.join(root, "build", "adele-nsis-installSection.nsh");

const require = createRequire(import.meta.url);
let ablRoot;
try {
  ablRoot = path.dirname(require.resolve("app-builder-lib/package.json"));
} catch {
  console.warn("[apply-nsis-installsection] app-builder-lib not found, skip.");
  process.exit(0);
}

const dest = path.join(ablRoot, "templates", "nsis", "installSection.nsh");

if (!existsSync(src)) {
  console.error("[apply-nsis-installsection] missing source:", src);
  process.exit(1);
}

copyFileSync(src, dest);
console.log("[apply-nsis-installsection] applied ADELE installSection ->", dest);
