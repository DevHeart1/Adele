const fs = require("fs");
const path = require("path");
const ResEdit = require("resedit");

exports.default = async function stampWindowsIcon(context) {
  if (context.electronPlatformName !== "win32") {
    return;
  }

  const productName = context.packager.appInfo.productFilename;
  const version = context.packager.appInfo.version || "1.0.0";
  const exePath = path.join(context.appOutDir, `${productName}.exe`);
  const iconPath = path.join(context.packager.projectDir, "build", "icon.ico");

  if (!fs.existsSync(exePath)) {
    throw new Error(`[stamp-windows-icon] Missing executable: ${exePath}`);
  }

  if (!fs.existsSync(iconPath)) {
    throw new Error(`[stamp-windows-icon] Missing icon: ${iconPath}`);
  }

  const exe = ResEdit.NtExecutable.from(fs.readFileSync(exePath), {
    ignoreCert: true,
  });
  const resources = ResEdit.NtExecutableResource.from(exe);
  const iconFile = ResEdit.Data.IconFile.from(fs.readFileSync(iconPath));

  ResEdit.Resource.IconGroupEntry.replaceIconsForResource(
    resources.entries,
    1,
    1033,
    iconFile.icons.map((item) => item.data)
  );

  const language = { lang: 1033, codepage: 1200 };
  const versionEntries = ResEdit.Resource.VersionInfo.fromEntries(resources.entries);
  const versionInfo = versionEntries[0] || ResEdit.Resource.VersionInfo.createEmpty();
  versionInfo.setFileVersion(version);
  versionInfo.setProductVersion(version);
  versionInfo.setStringValues(language, {
    CompanyName: "Startrz Technologies",
    FileDescription: "ADELE",
    FileVersion: version,
    InternalName: "ADELE",
    LegalCopyright: "Copyright (C) 2026 Startrz Technologies",
    OriginalFilename: "ADELE.exe",
    ProductName: "ADELE",
    ProductVersion: version,
  });
  versionInfo.outputToResourceEntries(resources.entries);

  resources.outputResource(exe);
  fs.writeFileSync(exePath, Buffer.from(exe.generate()));
  console.log(`[stamp-windows-icon] Stamped ADELE icon and version metadata into ${exePath}`);

  // The helper is optional: the island is disabled by default and the core app
  // must package normally on machines without Rust. A release that explicitly
  // runs build:island:win carries the helper alongside other resources.
  const bridgeSource = path.join(context.packager.projectDir, "build", "island", "adele-island-bridge.exe");
  if (fs.existsSync(bridgeSource)) {
    const bridgeTarget = path.join(context.appOutDir, "resources", "adele-island-bridge.exe");
    fs.copyFileSync(bridgeSource, bridgeTarget);
    console.log(`[stamp-windows-icon] Added optional island bridge: ${bridgeTarget}`);
  }
};
