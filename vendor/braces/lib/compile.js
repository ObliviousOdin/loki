'use strict';

const fill = require('fill-range');
const utils = require('./utils');

const compile = (ast, options = {}) => {
  const frames = [{ node: ast, parent: {}, output: '', index: 0 }];
  const active = new Set();
  let result;
  const finish = value => {
    active.delete(frames.pop().node);
    if (frames.length) frames[frames.length - 1].output += value;
    else result = value;
  };

  while (frames.length) {
    const frame = frames[frames.length - 1];
    const { node, parent } = frame;
    if (frame.entered) {
      if (node.nodes && frame.index < node.nodes.length) {
        frames.push({ node: node.nodes[frame.index++], parent: node, output: '', index: 0 });
      } else {
        finish(frame.output);
      }
      continue;
    }
    if (active.has(node)) throw utils.cycleError();
    active.add(node);
    frame.entered = true;
    const invalidBlock = utils.isInvalidBrace(parent);
    const invalidNode = node.invalid === true && options.escapeInvalid === true;
    const invalid = invalidBlock === true || invalidNode === true;
    const prefix = options.escapeInvalid === true ? '\\' : '';

    if (node.isOpen === true || node.isClose === true) {
      if (node.isOpen !== true && node.isClose === true) console.log('node.isClose', prefix, node.value);
      finish(prefix + node.value);
      continue;
    }
    if (node.type === 'open' || node.type === 'close') {
      finish(invalid ? prefix + node.value : node.type === 'open' ? '(' : ')');
      continue;
    }
    if (node.type === 'comma') {
      finish(node.prev.type === 'comma' ? '' : invalid ? node.value : '|');
      continue;
    }
    if (node.value) {
      finish(node.value);
      continue;
    }
    if (node.nodes && node.ranges > 0) {
      const args = utils.reduce(node.nodes);
      const range = fill(...args, { ...options, wrap: false, toRegex: true, strictZeros: true });
      if (range.length !== 0) {
        finish(args.length > 1 && range.length > 1 ? '(' + range + ')' : range);
      }
    }
  }
  return result;
};

module.exports = compile;
