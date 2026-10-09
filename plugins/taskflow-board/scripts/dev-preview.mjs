import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const htmlPath = join(here, "..", "ui", "board.html");
const port = Number(process.env.PORT || 4173);

const server = createServer(async (request, response) => {
  if (request.url !== "/" && request.url !== "/board.html") {
    response.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
    response.end("Not found");
    return;
  }
  response.writeHead(200, {
    "content-type": "text/html; charset=utf-8",
    "cache-control": "no-store",
  });
  response.end(await readFile(htmlPath));
});

server.listen(port, "127.0.0.1", () => {
  process.stdout.write(`Taskflow preview: http://127.0.0.1:${port}\n`);
});
