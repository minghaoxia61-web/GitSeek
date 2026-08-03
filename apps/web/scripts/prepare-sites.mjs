import { mkdir, writeFile } from "node:fs/promises";

const worker = `export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith("/api/") || url.pathname === "/health") {
      return new Response(JSON.stringify({
        detail: "The public UI is running in demonstration mode. Connect an OpenScout API deployment for live search."
      }), {
        status: 503,
        headers: { "content-type": "application/json; charset=utf-8" }
      });
    }
    return env.ASSETS.fetch(request);
  }
};
`;

await mkdir("dist/server", { recursive: true });
await writeFile("dist/server/index.js", worker, "utf8");
