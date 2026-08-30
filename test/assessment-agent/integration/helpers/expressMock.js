'use strict';

const qs = require('qs');

const METHODS = ['get', 'post', 'put', 'delete', 'patch', 'head', 'options'];

function flatten(arr) {
  return arr.reduce((acc, item) => acc.concat(Array.isArray(item) ? flatten(item) : [item]), []);
}

function normalizePath(p) {
  if (typeof p !== 'string' || !p) return '/';
  let out = p;
  if (!out.startsWith('/')) out = '/' + out;
  if (out.length > 1 && out.endsWith('/')) out = out.replace(/\/+$/, '');
  return out;
}

function parseQuery(url) {
  const idx = String(url || '').indexOf('?');
  if (idx === -1) return {};
  return qs.parse(String(url).slice(idx + 1));
}

function compilePath(template) {
  const segments = template.split('/').filter(Boolean);
  const keys = [];
  const parts = [];
  for (const seg of segments) {
    if (seg.startsWith(':')) {
      keys.push(seg.slice(1));
      parts.push('([^/]+)');
    } else {
      parts.push(seg.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    }
  }
  return { keys, regex: new RegExp('^/' + parts.join('/') + '/?$') };
}

function matchPath(template, pathname) {
  if (template === '/') return {};
  const { keys, regex } = compilePath(template);
  const m = regex.exec(pathname);
  if (!m) return null;
  const params = {};
  keys.forEach((k, i) => { params[k] = decodeURIComponent(m[i + 1]); });
  return params;
}

function isRouter(fn) {
  return typeof fn === 'function' && Array.isArray(fn.stack);
}

function augment(req, res) {
  req.path = String(req.url || '/').split('?')[0];
  req.query = parseQuery(req.url);
  req.params = req.params || {};
  req.body = req.body || {};
  if (!res.status) {
    res.status = function status(code) {
      res.statusCode = code;
      return res;
    };
  }
  if (!res.json) {
    res.json = function json(body) {
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify(body));
    };
  }
  if (!res.send) {
    res.send = function send(body) {
      if (body && typeof body === 'object') {
        res.json(body);
      } else {
        res.end(body == null ? undefined : String(body));
      }
    };
  }
}

function runHandlers(handlers, req, res, continueAt) {
  const remaining = handlers.slice();

  return (function step(err) {
    if (err) return continueAt(err);
    if (res.writableEnded) return;
    if (remaining.length === 0) return continueAt();

    const handler = remaining.shift();
    let called = false;
    const done = (e) => {
      if (called) return;
      called = true;
      step(e);
    };

    let ret;
    try {
      ret = handler(req, res, done);
    } catch (e) {
      return done(e);
    }

    if (ret && typeof ret.then === 'function') {
      ret.then(
        () => { if (!called && !res.writableEnded) done(); },
        (e) => done(e)
      );
    }
    return undefined;
  })();
}

function createRouter() {
  const stack = [];

  const router = function boundRouter(req, res, outerDone) {
    let i = 0;
    let pendingError = null;

    (function innerNext(err) {
      if (err) pendingError = err;

      while (i < stack.length) {
        if (res.writableEnded) return;
        const layer = stack[i++];
        const isErrorLayer = layer.handlers.length === 1 && layer.handlers[0].length >= 4;

        if (pendingError) {
          if (isErrorLayer && matchPath(layer.path, req.path) !== null) {
            return runHandlers(layer.handlers, req, res, innerNext);
          }
          continue;
        }

        if (layer.method && layer.method !== (req.method || 'GET').toUpperCase()) continue;

        const params = matchPath(layer.path, req.path);
        if (params === null) continue;
        if (Object.keys(params).length) Object.assign(req.params || {}, params);

        return runHandlers(layer.handlers, req, res, innerNext);
      }

      if (outerDone) outerDone(pendingError || undefined);
    })();
  };

  router.stack = stack;

  METHODS.forEach((m) => {
    router[m] = (path, ...rest) => {
      stack.push({ method: m.toUpperCase(), path: normalizePath(path), handlers: flatten(rest) });
      return router;
    };
  });

  return router;
}

function createApp() {
  const stack = [];

  const app = function app(req, res) {
    dispatch(stack, req, res);
  };

  app.stack = stack;

  app.use = function use(arg, ...rest) {
    if (typeof arg === 'function') {
      stack.push({ method: null, path: '/', handlers: flatten([arg, ...rest]) });
    } else {
      stack.push({ method: null, path: normalizePath(arg), handlers: flatten(rest) });
    }
    return app;
  };

  METHODS.forEach((m) => {
    app[m] = (path, ...rest) => {
      stack.push({ method: m.toUpperCase(), path: normalizePath(path), handlers: flatten(rest) });
      return app;
    };
  });

  app.listen = () => app;
  return app;
}

function dispatch(stack, req, res) {
  augment(req, res);

  let i = 0;
  let pendingError = null;

  function next(err) {
    if (err) pendingError = err;

    while (i < stack.length) {
      if (res.writableEnded) return;

      const layer = stack[i++];
      const isErrorLayer = layer.handlers.length === 1 && layer.handlers[0].length >= 4;
      const isMount = isRouter(layer.handlers[0]) && layer.path !== '/';

      if (isMount) {
        const prefixOk =
          req.path === layer.path ||
          req.path.startsWith(layer.path + '/');
        if (!prefixOk) continue;

        const prev = {
          url: req.url,
          path: req.path,
          query: req.query,
          params: req.params,
        };

        const remainder = String(req.url).slice(layer.path.length) || '/';
        req.url = remainder;
        req.path = String(remainder).split('?')[0] || '/';
        req.query = parseQuery(remainder);
        req.params = {};

        return runHandlers(layer.handlers, req, res, (e) => {
          req.url = prev.url;
          req.path = prev.path;
          req.query = prev.query;
          req.params = prev.params;
          next(e);
        });
      }

      if (pendingError) {
        if (!isErrorLayer) continue;
        const params = matchPath(layer.path, req.path);
        if (params === null) continue;
        if (Object.keys(params).length) Object.assign(req.params || {}, params);
        return runHandlers(layer.handlers, req, res, next);
      }

      if (layer.method && layer.method !== (req.method || 'GET').toUpperCase()) continue;

      const params = matchPath(layer.path, req.path);
      if (params === null) continue;
      if (Object.keys(params).length) Object.assign(req.params || {}, params);

      return runHandlers(layer.handlers, req, res, next);
    }

    res.setHeader('Content-Type', 'application/json');
    if (pendingError) {
      const body = { success: false, message: pendingError.message || 'Internal server error' };
      if (pendingError.error) body.error = pendingError.error;
      res.statusCode = pendingError.statusCode || pendingError.status || 500;
      res.end(JSON.stringify(body));
    } else {
      res.statusCode = 404;
      res.end(JSON.stringify({ success: false, message: 'Route ' + (req.method || 'GET') + ' ' + req.path + ' not found' }));
    }
  }

  next();
}

function jsonParser() {
  return (req, res, next) =>
    new Promise((resolve) => {
      const ct = String(req.headers['content-type'] || '').toLowerCase();
      if (!ct.includes('json')) {
        req.body = req.body || {};
        resolve();
        next();
        return;
      }

      let raw = '';
      req.setEncoding('utf8');
      req.on('data', (chunk) => { raw += chunk; });
      req.on('end', () => {
        req.body = {};
        if (raw) {
          try {
            req.body = JSON.parse(raw);
          } catch (e) {
            req.body = {};
          }
        }
        resolve();
        next();
      });
      req.on('error', () => {
        req.body = {};
        resolve();
        next();
      });
    });
}

function urlencodedParser() {
  return (req, res, next) => {
    const ct = String(req.headers['content-type'] || '').toLowerCase();
    if (ct.includes('x-www-form-urlencoded')) {
      return jsonParser()(req, res, next);
    }
    return next();
  };
}

function expressMock() {
  return createApp();
}

expressMock.Router = createRouter;
expressMock.json = jsonParser;
expressMock.urlencoded = urlencodedParser;
expressMock.static = () => (req, res, next) => next();

module.exports = expressMock;