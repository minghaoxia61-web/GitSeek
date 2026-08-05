import { copyFile, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { extname, relative, resolve, sep } from "node:path";

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
};

const outputDirectory = resolve("dist");
const entries = await readdir(outputDirectory, { recursive: true, withFileTypes: true });
const assets = {};

for (const entry of entries) {
  if (!entry.isFile()) continue;

  const absolutePath = resolve(entry.parentPath, entry.name);
  const assetPath = relative(outputDirectory, absolutePath).split(sep).join("/");
  if (assetPath.startsWith("server/") || assetPath.startsWith(".openai/")) continue;

  assets[`/${assetPath}`] = {
    body: (await readFile(absolutePath)).toString("base64"),
    type: contentTypes[extname(entry.name)] ?? "application/octet-stream",
  };
}

const worker = `const assets = ${JSON.stringify(assets)};

function decode(base64) {
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/") || url.pathname === "/health") {
      return new Response(JSON.stringify({
        detail: "The public UI is running in demonstration mode. Connect an OpenScout API deployment for live search."
      }), {
        status: 503,
        headers: { "content-type": "application/json; charset=utf-8" }
      });
    }

    const requestedAsset = assets[url.pathname];
    const asset = requestedAsset ?? assets["/index.html"];
    if (!asset) return new Response("Not found", { status: 404 });

    return new Response(request.method === "HEAD" ? null : decode(asset.body), {
      headers: {
        "content-type": asset.type,
        "cache-control": requestedAsset && url.pathname !== "/index.html"
          ? "public, max-age=31536000, immutable"
          : "no-cache"
      }
    });
  }
};
`;

await mkdir("dist/server", { recursive: true });
await mkdir("dist/.openai", { recursive: true });
await writeFile("dist/server/index.js", worker, "utf8");
await copyFile(".openai/hosting.json", "dist/.openai/hosting.json");
