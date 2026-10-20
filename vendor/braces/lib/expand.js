'use strict';

const fill = require('fill-range');
const stringify = require('./stringify');
const utils = require('./utils');

// The call frames preserve append's ordering and empty-array identity cases.
const append = (queue = '', stash = '', enclose = false) => {
  const active = new Set();
  const frame = (q, s, source) => {
    if (source && active.has(source)) throw utils.cycleError();
    if (source) active.add(source);
    return { queue: [].concat(q), stash: [].concat(s), result: [], index: 0, inner: 0, source };
  };
  const frames = [frame(queue, stash)];
  let result;
  const finish = value => {
    active.delete(frames.pop().source);
    if (frames.length) frames[frames.length - 1].result.push(value);
    else result = value;
  };
  while (frames.length) {
    const current = frames[frames.length - 1];
    if (!current.stash.length) {
      finish(current.queue);
      continue;
    }
    if (!current.queue.length) {
      finish(enclose ? utils.flatten(current.stash).map(ele => '{' + ele + '}') : current.stash);
      continue;
    }
    if (current.index >= current.queue.length) {
      finish(utils.flatten(current.result));
      continue;
    }
    const item = current.queue[current.index];
    const values = Array.isArray(item) ? item : current.stash;
    if (current.inner >= values.length) {
      current.index++;
      current.inner = 0;
      continue;
    }
    let value = values[current.inner++];
    if (Array.isArray(item)) {
      frames.push(frame(value, current.stash, item));
    } else {
      if (enclose === true && typeof value === 'string') value = '{' + value + '}';
      if (Array.isArray(value)) frames.push(frame(item, value, value));
      else current.result.push(item + value);
    }
  }
  return result;
};

const expand = (ast, options = {}) => {
  const rangeLimit = options.rangeLimit === undefined ? 1000 : options.rangeLimit;
  const frames = [{ node: ast, parentQueue: undefined, index: 0 }];
  const active = new Set();
  let result;
  const finish = value => {
    active.delete(frames.pop().node);
    if (!frames.length) result = value;
  };
  while (frames.length) {
    const frame = frames[frames.length - 1];
    const { node, parentQueue: q } = frame;
    if (!frame.entered) {
      if (active.has(node)) throw utils.cycleError();
      active.add(node);
      frame.entered = true;
      node.queue = [];
      if (node.invalid || node.dollar) {
        q.push(append(q.pop(), stringify(node, options)));
        finish();
        continue;
      }
      if (node.type === 'brace' && node.invalid !== true && node.nodes.length === 2) {
        q.push(append(q.pop(), ['{}']));
        finish();
        continue;
      }
      if (node.nodes && node.ranges > 0) {
        const args = utils.reduce(node.nodes);
        if (utils.exceedsLimit(...args, options.step, rangeLimit)) {
          throw new RangeError('expanded array length exceeds range limit. Use options.rangeLimit to increase or disable the limit.');
        }
        let range = fill(...args, options);
        if (range.length === 0) range = stringify(node, options);
        q.push(append(q.pop(), range));
        node.nodes = [];
        finish();
        continue;
      }
      frame.enclose = utils.encloseBrace(node);
      // Traversal owns work queues; caller-supplied parent links are metadata.
      frame.queue = node.type === 'brace' || node.type === 'root' || q === undefined ? node.queue : q;
    }
    const { queue, enclose } = frame;
    if (frame.index >= node.nodes.length) {
      finish(queue);
      continue;
    }
    const index = frame.index++;
    const child = node.nodes[index];
    if (child.type === 'comma' && node.type === 'brace') {
      if (index === 1) queue.push('');
      queue.push('');
    } else if (child.type === 'close') {
      q.push(append(q.pop(), queue, enclose));
    } else if (child.value && child.type !== 'open') {
      queue.push(append(queue.pop(), child.value));
    } else if (child.nodes) {
      frames.push({ node: child, parentQueue: queue, index: 0 });
    }
  }
  return utils.flatten(result);
};

module.exports = expand;
