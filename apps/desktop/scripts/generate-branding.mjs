#!/usr/bin/env node
/**
 * Generates every ADELE app/installer icon from the onboarding welcome mark.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import pngToIco from "png-to-ico";
import sharp from "sharp";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.join(__dirname, "..");
const buildDir = path.join(root, "build");
const rendererAssetsDir = path.join(root, "renderer", "assets");
const extensionIconsDir = path.join(root, "chrome_extension", "icons");

const MARK_PATHS = `
  <path d="M27 5c3.7 8.5 8.3 13.1 16.7 16.7l-4.8 11.6c-8.5-3.7-13.1-8.3-16.7-16.7L27 5Z" />
  <path d="M21.8 21.3c8.5 3.7 13.1 8.3 16.7 16.7L27 43c-3.7-8.5-8.3-13.1-16.7-16.7l11.5-5Z" />
`;

function iconSvg(size = 1024) {
  return Buffer.from(`
    <svg width="${size}" height="${size}" viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="bg" cx="50%" cy="38%" r="68%">
          <stop offset="0%" stop-color="#1b2410"/>
          <stop offset="62%" stop-color="#111111"/>
          <stop offset="100%" stop-color="#070807"/>
        </radialGradient>
        <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="13" result="blur"/>
          <feColorMatrix in="blur" type="matrix" values="0 0 0 0 0.72 0 0 0 0 1 0 0 0 0 0.17 0 0 0 0.75 0"/>
          <feMerge>
            <feMergeNode/>
            <feMergeNode in="SourceGraphic"/>
          </feMerge>
        </filter>
      </defs>
      <rect width="1024" height="1024" rx="226" fill="url(#bg)"/>
      <circle cx="512" cy="512" r="300" fill="none" stroke="#b8ff2c" stroke-opacity="0.11" stroke-width="20"/>
      <circle cx="512" cy="512" r="184" fill="#b8ff2c" opacity="0.08"/>
      <g transform="translate(243 234) scale(8.9) rotate(-20 32 32)" fill="#b8ff2c" filter="url(#glow)">
        ${MARK_PATHS}
      </g>
    </svg>
  `);
}

async function makePng(size) {
  return sharp(iconSvg(size)).png().toBuffer();
}

async function writePngs() {
  const png1024 = await makePng(1024);
  fs.writeFileSync(path.join(root, "icon.png"), png1024);
  fs.writeFileSync(path.join(buildDir, "icon.png"), png1024);
  fs.writeFileSync(path.join(rendererAssetsDir, "icon.png"), png1024);
  fs.writeFileSync(path.join(rendererAssetsDir, "favicon.png"), await makePng(256));
}

async function writeExtensionIcons() {
  fs.mkdirSync(extensionIconsDir, { recursive: true });
  const sizes = [16, 32, 48, 128];
  for (const size of sizes) {
    const png = await makePng(size);
    fs.writeFileSync(path.join(extensionIconsDir, `icon-${size}.png`), png);
  }
}

async function writeIco() {
  const icoPng = await makePng(256);
  const ico = await pngToIco(icoPng);
  fs.writeFileSync(path.join(buildDir, "icon.ico"), ico);
  fs.writeFileSync(path.join(buildDir, "installerIcon.ico"), ico);

  const distIconDir = path.join(root, "dist", ".icon-ico");
  if (fs.existsSync(distIconDir)) {
    fs.writeFileSync(path.join(distIconDir, "icon.ico"), ico);
  }
}

async function writeIcns() {
  const entries = [
    ["icp4", 16],
    ["icp5", 32],
    ["icp6", 64],
    ["ic07", 128],
    ["ic08", 256],
    ["ic09", 512],
    ["ic10", 1024],
  ];
  const chunks = await Promise.all(entries.map(async ([type, size]) => {
    const png = await makePng(size);
    const header = Buffer.alloc(8);
    header.write(type, 0, "ascii");
    header.writeUInt32BE(8 + png.length, 4);
    return Buffer.concat([header, png]);
  }));
  const length = 8 + chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const header = Buffer.alloc(8);
  header.write("icns", 0, "ascii");
  header.writeUInt32BE(length, 4);
  fs.writeFileSync(path.join(buildDir, "icon.icns"), Buffer.concat([header, ...chunks], length));
}

/** NSIS wizard sidebar BMP: 164x314 24-bit RGB, padded rows. */
async function writeSidebarBmp(filePath) {
  const W = 164;
  const H = 314;
  const rowStride = ((W * 3 + 3) >> 2) << 2;
  const imageSize = rowStride * H;
  const pixelOffset = 14 + 40;
  const fileSize = pixelOffset + imageSize;
  const pixels = Buffer.alloc(W * H * 3);

  const setPixel = (x, y, r, g, b) => {
    if (x < 0 || x >= W || y < 0 || y >= H) return;
    const i = (y * W + x) * 3;
    pixels[i] = b;
    pixels[i + 1] = g;
    pixels[i + 2] = r;
  };

  const blendPixel = (x, y, r, g, b, a) => {
    if (x < 0 || x >= W || y < 0 || y >= H || a <= 0) return;
    const i = (y * W + x) * 3;
    pixels[i] = Math.round(pixels[i] * (1 - a) + b * a);
    pixels[i + 1] = Math.round(pixels[i + 1] * (1 - a) + g * a);
    pixels[i + 2] = Math.round(pixels[i + 2] * (1 - a) + r * a);
  };

  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const v = y / (H - 1);
      setPixel(x, y, Math.round(8 + 7 * (1 - v)), Math.round(10 + 16 * (1 - v)), Math.round(7 + 5 * (1 - v)));
      const ring = Math.abs(Math.hypot(x + 48, y - 244) - 136);
      if (ring < 18) blendPixel(x, y, 184, 255, 44, ((18 - ring) / 18) * 0.18);
      const beam = Math.abs((x - 24) - (y - 88) * 0.58);
      if (beam < 13 && y > 94) blendPixel(x, y, 184, 255, 44, ((13 - beam) / 13) * 0.13);
      if ((x + y) % 5 === 0) blendPixel(x, y, 255, 255, 255, 0.014);
    }
  }

  const mark = await sharp(iconSvg(128)).resize(76, 76).raw().ensureAlpha().toBuffer();
  const ox = Math.round((W - 76) / 2);
  const oy = 28;
  for (let y = 0; y < 76; y++) {
    for (let x = 0; x < 76; x++) {
      const src = (y * 76 + x) * 4;
      const alpha = mark[src + 3] / 255;
      if (alpha <= 0.01) continue;
      blendPixel(ox + x, oy + y, mark[src], mark[src + 1], mark[src + 2], alpha);
    }
  }

  const buf = Buffer.alloc(fileSize);
  buf.write("BM", 0);
  buf.writeUInt32LE(fileSize, 2);
  buf.writeUInt16LE(0, 6);
  buf.writeUInt16LE(0, 8);
  buf.writeUInt32LE(pixelOffset, 10);
  buf.writeUInt32LE(40, 14);
  buf.writeUInt32LE(W, 18);
  buf.writeInt32LE(H, 22);
  buf.writeUInt16LE(1, 26);
  buf.writeUInt16LE(24, 28);
  buf.writeUInt32LE(0, 30);
  buf.writeUInt32LE(imageSize, 34);
  buf.writeInt32LE(2835, 38);
  buf.writeInt32LE(2835, 42);
  buf.writeUInt32LE(0, 46);
  buf.writeUInt32LE(0, 50);

  for (let y = 0; y < H; y++) {
    const dst = pixelOffset + (H - 1 - y) * rowStride;
    pixels.copy(buf, dst, y * W * 3, y * W * 3 + W * 3);
  }
  fs.writeFileSync(filePath, buf);
}

async function main() {
  fs.mkdirSync(buildDir, { recursive: true });
  fs.mkdirSync(rendererAssetsDir, { recursive: true });

  await writePngs();
  await writeExtensionIcons();
  await writeIco();
  await writeIcns();
  await writeSidebarBmp(path.join(buildDir, "installerSidebar.bmp"));

  console.log("[branding] Wrote ADELE welcome-mark icons: icon.png, build/icon.png, build/icon.ico, build/icon.icns, build/installerIcon.ico, build/installerSidebar.bmp, renderer/assets/favicon.png, chrome_extension/icons/icon-{16,32,48,128}.png");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
