import fs from "node:fs";
import path from "node:path";
import process from "node:process";

const root = path.resolve(import.meta.dirname, "..");
const source = path.join(root, "native", "adele-island-bridge", "target", "release", "adele-island-bridge.exe");
const targetDirectory = path.join(root, "build", "island");
const target = path.join(targetDirectory, "adele-island-bridge.exe");

if (!fs.existsSync(source)) {
  console.log("[island] Native bridge not built; disabled-by-default island package will omit it.");
  process.exit(0);
}

fs.mkdirSync(targetDirectory, { recursive: true });
fs.copyFileSync(source, target);
console.log(`[island] Prepared ${target}`);
