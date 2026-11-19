import { createReadStream, statSync } from "node:fs";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const mime = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".otf": "font/otf",
};

const server = createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, "http://localhost").pathname);
  const relative = normalize(pathname === "/" ? "index.html" : pathname.slice(1));
  if (relative.startsWith("..")) {
    response.writeHead(403).end("Forbidden");
    return;
  }
  const filename = join(root, relative);
  try {
    const stat = statSync(filename);
    if (!stat.isFile()) throw new Error("not a file");
    response.writeHead(200, {
      "Content-Type": mime[extname(filename)] ?? "application/octet-stream",
      "Cache-Control": "no-store",
    });
    createReadStream(filename).pipe(response);
  } catch {
    response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }).end("Not found");
  }
});

const preferred = Number(process.env.PORT ?? 4173);
let port = preferred;
server.on("error", (error) => {
  if (error.code === "EADDRINUSE" && port < preferred + 20) {
    port += 1;
    server.listen(port, "127.0.0.1");
  } else {
    console.error(error);
    process.exitCode = 1;
  }
});
server.on("listening", () => {
  console.log(`DQS / LBS lab: http://127.0.0.1:${port}`);
});
server.listen(port, "127.0.0.1");
