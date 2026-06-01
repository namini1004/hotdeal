import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const port = Number(process.env.PORT || 3000);

const mimeTypes = new Map([
  ['.html', 'text/html; charset=utf-8'],
  ['.js', 'text/javascript; charset=utf-8'],
  ['.mjs', 'text/javascript; charset=utf-8'],
  ['.css', 'text/css; charset=utf-8'],
  ['.json', 'application/json; charset=utf-8'],
  ['.svg', 'image/svg+xml'],
  ['.png', 'image/png'],
  ['.jpg', 'image/jpeg'],
  ['.jpeg', 'image/jpeg'],
  ['.webp', 'image/webp'],
  ['.ico', 'image/x-icon'],
  ['.txt', 'text/plain; charset=utf-8'],
  ['.xml', 'application/xml; charset=utf-8'],
  ['.webmanifest', 'application/manifest+json; charset=utf-8'],
]);

const apiRewrites = [
  [/^\/api\/deals\/([^/]+)\/?$/, '/api/deals.js'],
  [/^\/d\/([^/]+)\/?$/, '/api/share.js'],
];

function sendJson(res, statusCode, data) {
  res.statusCode = statusCode;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

async function parseBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  if (!chunks.length) return undefined;
  const raw = Buffer.concat(chunks).toString('utf8');
  const contentType = req.headers['content-type'] || '';
  if (contentType.includes('application/json')) {
    try {
      return JSON.parse(raw);
    } catch {
      return undefined;
    }
  }
  if (contentType.includes('application/x-www-form-urlencoded')) {
    return Object.fromEntries(new URLSearchParams(raw));
  }
  return raw;
}

function decorateResponse(res) {
  res.status = (code) => {
    res.statusCode = code;
    return res;
  };
  res.json = (data) => sendJson(res, res.statusCode || 200, data);
  res.send = (data) => {
    if (Buffer.isBuffer(data) || typeof data === 'string') return res.end(data);
    return res.json(data);
  };
  return res;
}

async function handleApi(req, res, url) {
  let apiPath = `${url.pathname}.js`;
  let rewrittenId = null;

  for (const [pattern, destination] of apiRewrites) {
    const match = url.pathname.match(pattern);
    if (match) {
      apiPath = destination;
      rewrittenId = match[1];
      break;
    }
  }

  const modulePath = path.join(root, apiPath);
  try {
    const moduleUrl = pathToFileURL(modulePath);
    moduleUrl.searchParams.set('t', String(Date.now()));
    const handlerModule = await import(moduleUrl.href);
    const handler = handlerModule.default || handlerModule;
    req.query = Object.fromEntries(url.searchParams);
    if (rewrittenId) req.query.id = rewrittenId;
    req.body = await parseBody(req);
    await handler(req, decorateResponse(res));
  } catch (error) {
    sendJson(res, 500, {
      error: 'Local API handler failed',
      detail: error instanceof Error ? error.message : String(error),
    });
  }
}

async function serveStatic(req, res, url) {
  const pathname = decodeURIComponent(url.pathname);
  const requested = pathname === '/' ? '/index.html' : pathname;
  const filePath = path.normalize(path.join(root, requested));

  if (!filePath.startsWith(root)) {
    res.statusCode = 403;
    res.end('Forbidden');
    return;
  }

  try {
    const info = await stat(filePath);
    if (info.isDirectory()) {
      const indexPath = path.join(filePath, 'index.html');
      await readFile(indexPath);
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      createReadStream(indexPath).pipe(res);
      return;
    }

    res.setHeader('Content-Type', mimeTypes.get(path.extname(filePath).toLowerCase()) || 'application/octet-stream');
    createReadStream(filePath).pipe(res);
  } catch {
    res.statusCode = 404;
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.end('Not found');
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || `127.0.0.1:${port}`}`);
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/d/')) {
    await handleApi(req, res, url);
    return;
  }
  await serveStatic(req, res, url);
});

server.listen(port, '127.0.0.1', () => {
  console.log(`hotdeal-site running at http://127.0.0.1:${port}`);
});
