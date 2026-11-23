// A minimal stand-in for the browser, just enough to run the page's script
// outside one. PAGE_IDS (every id in the markup) is defined before this file.

class FakeNode {
  constructor(tag) {
    this.tag = tag;
    this.attrs = {};
    this.children = [];
    this.listeners = {};
    this.text = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.value = "";
  }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  addEventListener(type, handler) { (this.listeners[type] = this.listeners[type] || []).push(handler); }
  append(...nodes) { this.children.push(...nodes.map(FakeNode.mustBeNode)); }
  replaceChildren(...nodes) { this.children = nodes.map(FakeNode.mustBeNode); }
  static mustBeNode(node) {
    // A real browser would silently turn an array or object into text here.
    if (!(node instanceof FakeNode)) throw new Error("something that is not an element was added to the page");
    return node;
  }
  get textContent() {
    return this.tag === "#text" ? this.text : this.children.map((child) => child.textContent).join("");
  }
  set textContent(value) {
    const node = new FakeNode("#text");
    node.text = String(value);
    this.children = [node];
  }
  getBoundingClientRect() { return { left: 0, width: 200 }; }

  // Test helpers, not part of the real DOM.
  fire(type, event) {
    const handlers = this.listeners[type] || [];
    return Promise.all(handlers.map((handler) => handler(Object.assign({ currentTarget: this }, event))));
  }
  descendants() {
    return this.children.flatMap((child) => [child, ...child.descendants()]);
  }
}

const pageNodes = {};
for (const id of PAGE_IDS) pageNodes[id] = new FakeNode("div");

const document = {
  getElementById(id) {
    if (!(id in pageNodes)) throw new Error("the script looked up #" + id + ", which is not in the markup");
    return pageNodes[id];
  },
  createElement: (tag) => new FakeNode(tag),
  createElementNS: (namespace, tag) => new FakeNode(tag),
  createTextNode(text) {
    const node = new FakeNode("#text");
    node.text = String(text);
    return node;
  },
};

const calls = [];     // every fetch the page makes: {path, options}
const routes = {};    // path -> response body, or a function of the request options
const streams = [];   // every EventSource the page opens
let fetchFails = false;

globalThis.fetch = async (path, options) => {
  calls.push({ path, options });
  if (fetchFails) throw new Error("network down");
  if (!(path in routes)) throw new Error("unexpected request for " + path);
  const body = typeof routes[path] === "function" ? routes[path](options) : routes[path];
  return { json: async () => JSON.parse(JSON.stringify(body)) };
};

globalThis.EventSource = class {
  constructor(url) {
    this.url = url;
    streams.push(this);
  }
};

// Timers are collected rather than run, so the scenario decides when time passes.
const timers = [];
globalThis.setTimeout = (callback) => timers.push(callback);

let reloads = 0;
globalThis.location = { port: "8000", reload() { reloads++; } };
