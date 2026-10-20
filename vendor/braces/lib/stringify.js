'use strict';

const utils = require('./utils');

module.exports = (ast, options = {}) => {
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
        frames.push({ node: node.nodes[frame.index++], parent: {}, output: '', index: 0 });
      } else {
        finish(frame.output);
      }
      continue;
    }
    if (active.has(node)) throw utils.cycleError();
    active.add(node);
    frame.entered = true;
    const invalidBlock = options.escapeInvalid && utils.isInvalidBrace(parent);
    const invalidNode = node.invalid === true && options.escapeInvalid === true;
    if (node.value) {
      finish((invalidBlock || invalidNode) && utils.isOpenOrClose(node) ? '\\' + node.value : node.value);
    }
  }
  return result;
};
