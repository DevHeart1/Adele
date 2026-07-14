#!/usr/bin/env node
// ═══════════════════════════════════════════════════════════════
//  ADELE — Package Chrome Extension for Distribution
//
//  Creates a customer-ready .zip of the Chrome extension with
//  an install guide (README) inside it.
//
//  Usage:
//    npm run dist:extension
//
//  Output:
//    dist/adele-browser-bridge.zip
// ═══════════════════════════════════════════════════════════════

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync, copyFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const EXT_SRC = join(ROOT, "chrome_extension");
const DIST = join(ROOT, "dist");
const STAGING = join(DIST, "adele-browser-bridge");

function psQuote(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

// ── Clean & create staging directory ──
if (existsSync(STAGING)) {
  rmSync(STAGING, { recursive: true, force: true });
}
mkdirSync(STAGING, { recursive: true });
mkdirSync(DIST, { recursive: true });

// ── Copy extension files ──
const SKIP = new Set([".bak", ".DS_Store"]);

function copyDir(src, dest) {
  mkdirSync(dest, { recursive: true });
  for (const entry of readdirSync(src, { withFileTypes: true })) {
    if (SKIP.has(entry.name) || entry.name.endsWith(".bak")) continue;
    const srcPath = join(src, entry.name);
    const destPath = join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      copyFileSync(srcPath, destPath);
    }
  }
}

console.log("📦 Copying extension files...");
copyDir(EXT_SRC, STAGING);

// ── Write the customer-friendly README inside the zip ──
const readmeContent = `# 🌙 ADELE Browser Bridge — Chrome Extension

## Quick Install (2 minutes)

### Step 1: Unzip
You've already done this! This folder contains the extension.

### Step 2: Open Chrome Extensions
1. Open Google Chrome
2. Type \`chrome://extensions\` in the address bar and press Enter
3. Turn ON "Developer mode" (toggle in the top-right corner)

### Step 3: Install the Extension
1. Click the "Load unpacked" button (top-left)
2. Select THIS folder (the one containing this README)
3. The "ADELE Browser Bridge" extension will appear in your list

### Step 4: Pin the Extension
1. Click the puzzle piece icon 🧩 in Chrome's toolbar
2. Click the pin 📌 next to "ADELE Browser Bridge"

### Step 5: Connect to ADELE
The extension connects automatically to the ADELE desktop app.
If you need to change settings:
1. Right-click the ADELE extension icon → "Options"
2. The default Bridge URL is \`ws://127.0.0.1:8765\` (local mode)
3. Click "Save Settings"

### Troubleshooting
- **Extension not connecting?** Make sure the ADELE desktop app is running
- **"Developer mode" warning?** This is normal for extensions not from the Chrome Web Store. Click "Dismiss" each time Chrome starts.
- **Need help?** Contact support@adele.ai

---
*ADELE Browser Bridge v1.0.0*
`;

writeFileSync(join(STAGING, "INSTALL.md"), readmeContent);
console.log("📝 Added INSTALL.md guide");

// ── Create zip ──
const zipPath = join(DIST, "adele-browser-bridge.zip");
if (existsSync(zipPath)) {
  rmSync(zipPath, { force: true });
}

if (process.platform === "win32") {
  execFileSync(
    "powershell",
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-Command",
      `Compress-Archive -LiteralPath ${psQuote(STAGING)} -DestinationPath ${psQuote(zipPath)} -Force`,
    ],
    { stdio: "inherit" }
  );
} else {
  execFileSync("zip", ["-r", zipPath, "adele-browser-bridge/"], {
    cwd: DIST,
    stdio: "inherit",
  });
}

console.log(`\n✅ Extension packaged: ${zipPath}`);
console.log(`   Size: ${(statSync(zipPath).size / 1024).toFixed(0)} KB\n`);

// ── Clean staging ──
rmSync(STAGING, { recursive: true, force: true });
