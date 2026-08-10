import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const version = process.argv.slice(2).find((value) => value !== "--")?.trim();
if (!version || !/^\d+\.\d+\.\d+$/.test(version)) {
  throw new Error("Version must use MAJOR.MINOR.PATCH, for example 0.2.0");
}

const desktopRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const webRoot = path.resolve(desktopRoot, "../web");

async function updateJson(file, mutate) {
  const payload = JSON.parse(await readFile(file, "utf8"));
  mutate(payload);
  await writeFile(file, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

await updateJson(path.join(desktopRoot, "package.json"), (payload) => { payload.version = version; });
await updateJson(path.join(desktopRoot, "src-tauri/tauri.conf.json"), (payload) => { payload.version = version; });

const cargoPath = path.join(desktopRoot, "src-tauri/Cargo.toml");
const cargo = await readFile(cargoPath, "utf8");
await writeFile(cargoPath, cargo.replace(/^version = "[^"]+"/m, `version = "${version}"`), "utf8");

const appInfoPath = path.join(webRoot, "src/appInfo.ts");
const appInfo = await readFile(appInfoPath, "utf8");
await writeFile(appInfoPath, appInfo.replace(/APP_VERSION = "[^"]+"/, `APP_VERSION = "${version}"`), "utf8");

console.log(`GitSeek version set to ${version}`);
