import fs from "node:fs/promises";
import path from "node:path";
import sharp from "sharp";

const root = path.resolve("landing");
const out = path.join(root, "assets");
await fs.mkdir(out, { recursive: true });

const lime = "#a6ff00";
const dark = "#020403";
const panel = "#071009";

function svg(width, height, body) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="9" result="blur"/>
      <feColorMatrix in="blur" type="matrix" values="0 0 0 0 0.55 0 0 0 0 1 0 0 0 0 0 0 0 0 .95 0"/>
      <feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <linearGradient id="screen" x1="0" x2="1" y1="0" y2="1">
      <stop offset="0" stop-color="#151515"/>
      <stop offset="1" stop-color="#050805"/>
    </linearGradient>
    <radialGradient id="limeFog" cx="72%" cy="45%" r="60%">
      <stop offset="0" stop-color="#a6ff00" stop-opacity=".34"/>
      <stop offset=".45" stop-color="#6dba00" stop-opacity=".11"/>
      <stop offset="1" stop-color="#020403" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="100%" height="100%" fill="${dark}"/>
  ${body}
</svg>`;
}

async function writePng(name, width, height, body) {
  const file = path.join(out, name);
  await sharp(Buffer.from(svg(width, height, body))).png().toFile(file);
  console.log(`[asset] ${file}`);
}

const mark = `<g filter="url(#glow)" fill="${lime}">
  <path d="M48 12c8 19 18 29 38 38L74 77C55 69 45 59 36 39L48 12Z"/>
  <path d="M36 43c19 8 29 18 38 38l-27 11C39 73 29 63 9 55l27-12Z"/>
</g>`;

await writePng("adele-mark.png", 96, 96, mark);

await writePng("hero-bg.png", 1600, 1000, `
  <rect width="1600" height="1000" fill="#020302"/>
  <rect width="1600" height="1000" fill="url(#limeFog)"/>
  <g opacity=".22" stroke="${lime}" stroke-width="1">
    ${Array.from({ length: 52 }, (_, i) => {
      const y = 70 + i * 17;
      const x = (i * 97) % 1500;
      return `<path d="M${x} ${y}h${90 + (i % 8) * 35}m${35 + (i % 4) * 22} 0h${55 + (i % 6) * 18}" />`;
    }).join("")}
  </g>
  <g opacity=".35" fill="${lime}">
    ${Array.from({ length: 120 }, (_, i) => `<circle cx="${(i * 137) % 1600}" cy="${(i * 73) % 1000}" r="${i % 3 === 0 ? 1.8 : 1}" />`).join("")}
  </g>
  <g opacity=".45" stroke="${lime}" fill="none">
    <path d="M24 150h95v-38h42"/>
    <path d="M1490 105h72v92"/>
    <path d="M1250 890h180v-80h104"/>
    <path d="M80 860h145v58h120"/>
  </g>
`);

function onboardingScreen(x, y, w, h, rot = 0) {
  const cx = x + w / 2;
  const cy = y + h / 2;
  return `<g transform="rotate(${rot} ${cx} ${cy})" filter="url(#glow)">
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="22" fill="url(#screen)" stroke="${lime}" stroke-opacity=".72"/>
    <text x="${x + 36}" y="${y + 62}" fill="#fff" font-size="24" font-family="Arial Black, Impact">Choose how to run your AI agent</text>
    <text x="${x + 38}" y="${y + 92}" fill="#b8beb3" font-size="13" font-family="Arial">Pick what works for you. You can switch anytime.</text>
    ${[0, 1, 2].map((i) => `<rect x="${x + 38 + i * ((w - 100) / 3)}" y="${y + 130}" width="${(w - 130) / 3}" height="${h - 185}" rx="17" fill="#1b1d1a" stroke="${i === 1 ? lime : "#3a4634"}"/>
      <rect x="${x + 62 + i * ((w - 100) / 3)}" y="${y + 160}" width="56" height="56" rx="14" fill="#30342d"/>
      <text x="${x + 63 + i * ((w - 100) / 3)}" y="${y + 250}" fill="${i === 1 ? "#fff" : "#b8beb3"}" font-size="20" font-weight="800" font-family="Arial"> ${["Ready to go", "Bring your own API key", "Free local models"][i]}</text>
      <text x="${x + 70 + i * ((w - 100) / 3)}" y="${y + 305}" fill="${lime}" font-size="17" font-family="Arial">✓</text>
      <text x="${x + 98 + i * ((w - 100) / 3)}" y="${y + 306}" fill="#e8ece2" font-size="14" font-family="Arial">${["One-click setup", "Connect Gemini", "Works offline"][i]}</text>
      <rect x="${x + 62 + i * ((w - 100) / 3)}" y="${y + h - 90}" width="${(w - 190) / 3}" height="42" rx="21" fill="${i === 1 ? "#eaf2f5" : "#252722"}"/>
    `).join("")}
  </g>`;
}

function voiceScreen(x, y, w, h, rot = 0) {
  const cx = x + w / 2;
  const cy = y + h / 2;
  return `<g transform="rotate(${rot} ${cx} ${cy})" filter="url(#glow)">
    <rect x="${x}" y="${y}" width="${w}" height="${h}" rx="22" fill="#181a17" stroke="${lime}" stroke-opacity=".72"/>
    <text x="${x + 38}" y="${y + 55}" fill="${lime}" font-size="13" font-weight="900" letter-spacing="3" font-family="Arial">STEP 6 OF 8</text>
    <text x="${x + 38}" y="${y + 94}" fill="#fff" font-size="30" font-family="Arial Black, Impact">Choose a voice</text>
    <text x="${x + 38}" y="${y + 135}" fill="#b6b9b1" font-size="15" font-family="Arial">Pick the ElevenLabs voice ADELE should use for spoken replies.</text>
    <rect x="${x + 38}" y="${y + 170}" width="${w - 76}" height="${h - 250}" rx="18" fill="#1d2b13" stroke="${lime}" opacity=".95"/>
    ${Array.from({ length: 10 }, (_, i) => {
      const col = i % 2;
      const row = Math.floor(i / 2);
      const xx = x + 64 + col * ((w - 150) / 2);
      const yy = y + 198 + row * 62;
      return `<rect x="${xx}" y="${yy}" width="${(w - 180) / 2}" height="48" rx="14" fill="#14200f" stroke="${lime}" stroke-opacity=".45"/>
        <rect x="${xx + 14}" y="${yy + 10}" width="30" height="30" rx="10" fill="${lime}"/>
        <text x="${xx + 55}" y="${yy + 26}" fill="#fff" font-size="17" font-weight="800" font-family="Arial">${["Roger", "Sarah", "Laura", "Charlie", "George", "Callum", "River", "Harry", "Liam", "Alice"][i]} - ${["Laid-Back", "Mature", "Quirky", "Confident", "Warm", "Husky", "Relaxed", "Fierce", "Energetic", "Clear"][i]}</text>
        <text x="${xx + 55}" y="${yy + 42}" fill="#9ea596" font-size="11" font-family="Arial">premade · conversational · ${i % 3 === 0 ? "male" : "female"}</text>`;
    }).join("")}
    <rect x="${x + w - 210}" y="${y + h - 72}" width="160" height="50" rx="17" fill="${lime}"/>
    <text x="${x + w - 171}" y="${y + h - 40}" fill="#071009" font-size="17" font-weight="900" font-family="Arial">Save &amp; Continue</text>
  </g>`;
}

await writePng("hero-product.png", 1050, 760, `
  <rect width="1050" height="760" fill="transparent"/>
  <rect x="620" y="150" width="240" height="240" fill="none" stroke="${lime}" stroke-opacity=".25"/>
  ${onboardingScreen(130, 40, 760, 390, -6)}
  ${voiceScreen(40, 335, 760, 360, 8)}
  <g transform="translate(870 320) scale(1.75)">${mark}</g>
`);

await writePng("feature-voice.png", 560, 360, `
  <rect width="560" height="360" fill="#04100b"/>
  <path d="M70 180c70-44 112-44 180 0" stroke="${lime}" stroke-width="3" fill="none" opacity=".25"/>
  <g stroke="${lime}" stroke-width="2" opacity=".8">
    ${Array.from({ length: 34 }, (_, i) => {
      const x = 160 + i * 5;
      const h = 20 + Math.sin(i * 1.7) * 45 + (i % 5) * 6;
      return `<path d="M${x} ${180 - h / 2}v${h}" />`;
    }).join("")}
  </g>
  <path d="M360 82c78 28 110 80 105 160c-58-2-106-29-143-82c18-10 31-36 38-78Z" fill="none" stroke="${lime}" opacity=".55"/>
  <circle cx="396" cy="168" r="104" fill="none" stroke="${lime}" opacity=".12"/>
`);

await writePng("feature-loop.png", 560, 360, `
  <rect width="560" height="360" fill="#04100b"/>
  <circle cx="280" cy="180" r="108" fill="none" stroke="${lime}" stroke-width="2" opacity=".5"/>
  <path d="M210 95c73-52 154-21 179 36" fill="none" stroke="${lime}" stroke-width="20" opacity=".22"/>
  <path d="M354 268c-74 51-156 20-180-37" fill="none" stroke="${lime}" stroke-width="20" opacity=".22"/>
  <g transform="translate(233 132) scale(.95)">${mark}</g>
  <text x="250" y="69" fill="${lime}" font-size="18" font-weight="900" font-family="Arial">SENSE</text>
  <text x="404" y="185" fill="${lime}" font-size="18" font-weight="900" font-family="Arial">PLAN</text>
  <text x="252" y="314" fill="${lime}" font-size="18" font-weight="900" font-family="Arial">ACT</text>
`);

await writePng("feature-browser.png", 640, 360, `
  <rect width="640" height="360" fill="#04100b"/>
  <rect x="74" y="58" width="310" height="230" rx="18" fill="#101510" stroke="${lime}" stroke-opacity=".4"/>
  <circle cx="98" cy="80" r="6" fill="#8cff00"/><circle cx="120" cy="80" r="6" fill="#5f8500"/><circle cx="142" cy="80" r="6" fill="#344c1a"/>
  <rect x="110" y="150" width="230" height="58" rx="29" fill="#061006" stroke="${lime}"/>
  <path d="M136 178h90" stroke="${lime}" stroke-width="6" opacity=".14"/>
  <path d="M420 170c45 15 83 35 120 70" stroke="${lime}" stroke-width="2" fill="none" stroke-dasharray="7 8"/>
  <rect x="472" y="68" width="74" height="74" rx="18" fill="#0c1508" stroke="${lime}" opacity=".9"/>
  <rect x="472" y="224" width="74" height="74" rx="18" fill="#0c1508" stroke="${lime}" opacity=".9"/>
  <path d="M304 190l62 134l22-54l58 14l-142-94Z" fill="${lime}" stroke="#061006" stroke-width="4"/>
`);

await writePng("feature-local.png", 640, 360, `
  <rect width="640" height="360" fill="#04100b"/>
  <g filter="url(#glow)">
    <path d="M312 118l154 68l-154 78l-154-78l154-68Z" fill="#172018" stroke="${lime}" opacity=".92"/>
    <path d="M158 186v52l154 82l154-82v-52l-154 78l-154-78Z" fill="#0d130d" stroke="${lime}" opacity=".55"/>
    <g transform="translate(265 151) scale(.9)">${mark}</g>
  </g>
  <g stroke="${lime}" opacity=".35">
    ${Array.from({ length: 18 }, (_, i) => `<path d="M${40 + i * 28} ${310 - (i % 4) * 15}l${90 + (i % 5) * 20}-70" />`).join("")}
  </g>
  <rect x="360" y="56" width="230" height="42" rx="12" fill="#0b110b" stroke="${lime}"/>
  <text x="383" y="82" fill="#fff" font-size="15" font-family="monospace">ADELE_DATA_DIR / ~/.adele</text>
`);

await writePng("footer-core.png", 520, 320, `
  <rect width="520" height="320" fill="#020403"/>
  <g filter="url(#glow)">
    <path d="M258 82l176 78l-176 92l-176-92l176-78Z" fill="#172018" stroke="${lime}" opacity=".9"/>
    <path d="M82 160v62l176 94l176-94v-62l-176 92l-176-92Z" fill="#0d130d" stroke="${lime}" opacity=".45"/>
    <g transform="translate(208 115) scale(.95)">${mark}</g>
  </g>
  <g stroke="${lime}" opacity=".32">
    ${Array.from({ length: 26 }, (_, i) => `<path d="M${20 + i * 19} ${286 - (i % 5) * 18}l${70 + (i % 4) * 18}-42" />`).join("")}
    ${Array.from({ length: 18 }, (_, i) => `<path d="M${430 + (i % 5) * 18} ${80 + i * 10}l-80 ${35 + (i % 4) * 9}" />`).join("")}
  </g>
  <g opacity=".55" fill="${lime}">
    ${Array.from({ length: 48 }, (_, i) => `<circle cx="${(i * 83) % 520}" cy="${(i * 47) % 320}" r="${i % 4 === 0 ? 1.8 : 1}" />`).join("")}
  </g>
`);

const miniScenes = [
  ["use-research.png", "Research anything", "Research: Best AI tools for productivity", "M340 165c55-22 92 6 105 55c-55 22-92-6-105-55Z"],
  ["use-forms.png", "Fill forms", "Submit Application", "M364 185l55 105l18-45l50 11l-123-71Z"],
  ["use-data.png", "Extract data", "Company   Role   Location   Date", "M80 90h400v180H80z"],
  ["use-email.png", "Email outreach", "Jane, loved what you're building...", "M88 92h390v210H88z"],
  ["use-schedule.png", "Schedule", "Reminder: Prepare deck", "M90 90h390v210H90z"],
  ["use-files.png", "File ops", "Q1_Report.pdf / Invoices_2025", "M360 140h70l32 30v90H335V140z"],
  ["use-dev.png", "Dev automation", "$ adele run deploy.py", "M80 82h430v230H80z"],
  ["use-learn.png", "Learn", "Explain: Quantum Computing", "M338 116c80 12 117 84 78 150c-73-8-115-71-78-150Z"],
];

for (const [name, title, text, shape] of miniScenes) {
  await writePng(name, 520, 300, `
    <rect width="520" height="300" fill="#040807"/>
    <rect x="28" y="42" width="464" height="214" rx="16" fill="#09100d" stroke="${lime}" stroke-opacity=".44"/>
    <text x="56" y="84" fill="#fff" font-size="18" font-weight="800" font-family="Arial">${title}</text>
    <text x="56" y="132" fill="#d9ded2" font-size="16" font-family="Arial">${text}</text>
    <path d="${shape}" fill="none" stroke="${lime}" stroke-width="2" filter="url(#glow)" opacity=".8"/>
    <rect x="56" y="208" width="210" height="38" rx="19" fill="#18270f" stroke="${lime}" stroke-opacity=".45"/>
    <text x="78" y="232" fill="${lime}" font-size="14" font-weight="900" font-family="Arial">COMMAND. DONE.</text>
  `);
}
