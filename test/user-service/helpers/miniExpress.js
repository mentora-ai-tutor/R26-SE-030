function normalise(p) {
  if (typeof p !== 'string') return '/';
  return p.startsWith('/') ? p : `/${p}`;
}

function isRouter(fn) {
  return typeof fn === 'function' && Array.isArray(fn.stack);
}

function pathJoin(a, b) {
  if (!a || a === '/') return b || '/';
  if (!b || b === '/') return a;
  return `${a.replace(/\/$/, '')}${b}`;
}

function stripBase(pathname, base) {
  if (!base) return pathname;
  if (pathname === base) return '/';
  if (pathname.startsWith(base)) return pathname.slice(base.length);
  return pathname;
}

function matchPath(layerPath, pathname, base, mount) {
  const rel = stripBase(pathname, base);
  if (layerPath === '/') return true;
  if (layerPath === rel) return true;
  if (!mount) return false;
  const nextChar = rel[layerPath.length];
  return rel.startsWith(layerPath) && (nextChar === '/' || nextChar === '?' || nextChar === undefined);
}

function defaultErrorHandler(err, req, res) {
  if (res.writableEnded) return;
  res.status(500).json({ success: false, error: err.message, code: 'INTERNAL_ERROR' });
}

function runStack(stack, req, res, base, done) {
  let i = 0;
  const next = (err) => {
    if (err) {
      while (i < stack.length) {
        const layer = stack[i++];
        if (typeof layer.fn === 'function' && layer.fn.length === 4) {
          return layer.fn(err, req, res, next);
        }
      }
      return defaultErrorHandler(err, req, res);
    }
    while (i < stack.length) {
      const layer = stack[i++];
      const fn = layer.fn;
      if (typeof fn !== 'function') continue;
      if (fn.length === 4) continue;
      if (layer.method && layer.method !== req.method) continue;
      if (!matchPath(layer.path, req.path, base, layer.mount)) continue;
      if (isRouter(fn)) {
        const childBase = layer.path === '/' ? base : pathJoin(base, layer.path);
        return runStack(fn.stack, req, res, childBase, next);
      }
      if (fn.length >= 3) {
        return fn(req, res, next);
      }
      return fn(req, res);
    }
    done();
  };
  next();
}

function prepareRequest(req) {
  let parsed;
  try {
    parsed = new URL(req.url, 'http://localhost');
  } catch (e) {
    parsed = { pathname: req.url || '/', searchParams: new URLSearchParams() };
  }
  req.path = parsed.pathname || '/';
  req.query = Object.fromEntries(parsed.searchParams.entries());
  req.params = req.params || {};
}

function augmentResponse(res) {
  if (res.__mentoraAugmented) return res;
  res.__mentoraAugmented = true;
  res.status = function (code) {
    res.statusCode = code;
    return res;
  };
  res.json = function (body) {
    const text = Buffer.isBuffer(body) ? body : JSON.stringify(body);
    if (!res.getHeader('Content-Type')) res.setHeader('Content-Type', 'application/json');
    res.end(text);
    return res;
  };
  res.send = function (body) {
    if (typeof body === 'object' && body !== null && !Buffer.isBuffer(body)) {
      res.setHeader('Content-Type', 'application/json');
      body = JSON.stringify(body);
    }
    res.end(body);
    return res;
  };
  res.set = function (name, value) {
    const values = Array.isArray(value) ? value : [value];
    values.forEach((v) => res.setHeader(name, v));
    return res;
  };
  res.type = function (t) {
    const map = { html: 'text/html; charset=utf-8', json: 'application/json', text: 'text/plain; charset=utf-8' };
    res.setHeader('Content-Type', map[t] || t);
    return res;
  };
  return res;
}

function jsonParser() {
  return function (req, res, next) {
    const ct = String(req.headers['content-type'] || '').toLowerCase();
    if (!ct.includes('application/json')) return next();
    let data = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      data += chunk;
    });
    req.on('end', () => {
      if (data) {
        try {
          req.body = JSON.parse(data);
        } catch (e) {
          req.body = {};
        }
      }
      next();
    });
  };
}

function urlencodedParser() {
  return function (req, res, next) {
    const ct = String(req.headers['content-type'] || '').toLowerCase();
    if (!ct.includes('application/x-www-form-urlencoded')) return next();
    let data = '';
    req.on('data', (chunk) => {
      data += chunk;
    });
    req.on('end', () => {
      if (data) {
        req.body = Object.fromEntries(new URLSearchParams(data));
      }
      next();
    });
  };
}

function createApp() {
  const stack = [];
  const app = function (req, res) {
    prepareRequest(req);
    augmentResponse(res);
    runStack(stack, req, res, '', () => {});
  };
  app.stack = stack;

  app.use = function (...args) {
    let path = '/';
    let fns = args;
    if (typeof args[0] === 'string') {
      path = normalise(args[0]);
      fns = args.slice(1);
    }
    for (const fn of fns) {
      if (typeof fn === 'function') stack.push({ path, fn, mount: true });
    }
    return app;
  };

  for (const method of ['get', 'post', 'put', 'patch', 'delete']) {
    app[method] = function (routePath, ...fns) {
      const p = normalise(routePath);
      for (const fn of fns) {
        if (typeof fn === 'function') stack.push({ path: p, method: method.toUpperCase(), fn });
      }
      return app;
    };
  }

  return app;
}

function express() {
  return createApp();
}

express.Router = function () {
  return createApp();
};
express.json = jsonParser;
express.urlencoded = urlencodedParser;

module.exports = express;