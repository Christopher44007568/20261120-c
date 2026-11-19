import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, extname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const port = Number(process.env.PORT || 4173);
const types = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const candidate = normalize(join(root, pathname === "/" ? "index.html" : pathname));
  if (candidate !== root && !candidate.startsWith(`${root}${sep}`)) {
    response.writeHead(403);
    response.end("Forbidden");
    return;
  }

  try {
    if (!statSync(candidate).isFile()) throw new Error("Not a file");
    response.writeHead(200, {
      "Content-Type": types[extname(candidate)] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    createReadStream(candidate).pipe(response);
  } catch {
    response.writeHead(404);
    response.end("Not found");
  }
}).listen(port, "127.0.0.1", () => {
  console.log(`ORIGIN SHIFT running at http://127.0.0.1:${port}`);
});
