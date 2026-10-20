'use strict';

const Module = require('module');

const fakes = {
  mongoose: require('./mongoose'),
  winston: require('./winston'),
  dotenv: require('./dotenv'),
};

let installed = false;

function install() {
  if (installed) return;
  installed = true;
  const originalLoad = Module._load;
  Module._load = function patchedLoad(request, parent, isMain) {
    if (Object.prototype.hasOwnProperty.call(fakes, request)) {
      return fakes[request];
    }
    return originalLoad.apply(this, arguments);
  };
}

install();

module.exports = { install };
