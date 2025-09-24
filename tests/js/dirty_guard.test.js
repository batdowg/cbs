const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

class FakeField {
  constructor(name, value, options = {}) {
    this.name = name;
    this.value = value;
    this.disabled = false;
    this.type = options.type || 'text';
    this.tagName = options.tagName || 'INPUT';
    this.checked = options.checked || false;
    this.multiple = options.multiple || false;
    this.options = options.options || [];
    this._listeners = {};
  }

  addEventListener(type, handler) {
    if (!this._listeners[type]) {
      this._listeners[type] = [];
    }
    this._listeners[type].push(handler);
  }

  removeEventListener(type, handler) {
    if (!this._listeners[type]) {
      return;
    }
    this._listeners[type] = this._listeners[type].filter((fn) => fn !== handler);
  }

  dispatch(type, event = {}) {
    const handlers = this._listeners[type] || [];
    const evt = {
      target: this,
      preventDefault: () => {},
      stopImmediatePropagation: () => {},
      ...event,
    };
    handlers.forEach((handler) => handler(evt));
    return evt;
  }
}

class FakeForm {
  constructor(elements) {
    this.elements = elements;
    this._listeners = {};
    this.attributes = {};
  }

  addEventListener(type, handler) {
    if (!this._listeners[type]) {
      this._listeners[type] = [];
    }
    this._listeners[type].push(handler);
  }

  removeEventListener(type, handler) {
    if (!this._listeners[type]) {
      return;
    }
    this._listeners[type] = this._listeners[type].filter((fn) => fn !== handler);
  }

  dispatch(type, event = {}) {
    const handlers = this._listeners[type] || [];
    const evt = {
      target: event.target || this,
      preventDefault: () => {},
      stopImmediatePropagation: () => {},
      ...event,
    };
    handlers.forEach((handler) => handler(evt));
    return evt;
  }

  hasAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name);
  }
}

function createContext() {
  const windowListeners = new Map();
  const window = {
    _listeners: windowListeners,
    location: { href: 'https://example.com/', assign() {}, replace() {} },
    addEventListener(type, handler) {
      if (!windowListeners.has(type)) {
        windowListeners.set(type, new Set());
      }
      windowListeners.get(type).add(handler);
    },
    removeEventListener(type, handler) {
      if (!windowListeners.has(type)) {
        return;
      }
      windowListeners.get(type).delete(handler);
      if (windowListeners.get(type).size === 0) {
        windowListeners.delete(type);
      }
    },
    confirm: () => true,
  };
  const document = {
    readyState: 'complete',
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };
  const sandbox = {
    window,
    document,
    console,
    setTimeout,
    clearTimeout,
    HTMLFormElement: FakeForm,
  };
  sandbox.globalThis = sandbox;
  return sandbox;
}

async function run() {
  const sandbox = createContext();
  const codePath = path.join(__dirname, '..', '..', 'app', 'static', 'js', 'dirty_guard.js');
  const code = fs.readFileSync(codePath, 'utf8');
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);

  const guardApi = sandbox.window.CBSDirtyGuard;
  assert.ok(guardApi, 'Dirty guard API should be available on window');

  const field = new FakeField('name', 'original');
  const form = new FakeForm([field]);
  const tracked = guardApi.registerForm(form);
  assert.strictEqual(tracked.isDirty, false, 'Form starts clean');
  assert.strictEqual(guardApi.manager.hasDirtyForm(), false, 'Manager reports clean');

  field.value = 'updated';
  form.dispatch('input', { target: field });
  assert.strictEqual(tracked.isDirty, true, 'Field change marks form dirty');
  assert.strictEqual(guardApi.manager.hasDirtyForm(), true, 'Manager sees dirty form');
  assert.strictEqual(sandbox.window._listeners.has('beforeunload'), true, 'beforeunload handler registered');

  let confirmCalls = 0;
  sandbox.window.confirm = () => {
    confirmCalls += 1;
    return false;
  };
  const confirmResult = guardApi.manager.confirmNavigation();
  assert.strictEqual(confirmCalls, 1, 'Confirm dialog invoked');
  assert.strictEqual(confirmResult, false, 'Navigation blocked when cancelled');

  sandbox.window.confirm = () => true;
  const confirmAllow = guardApi.manager.confirmNavigation();
  assert.strictEqual(confirmAllow, true, 'Navigation proceeds when confirmed');

  form.dispatch('submit');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.strictEqual(tracked.isDirty, false, 'Submitting clears dirty state');
  assert.strictEqual(guardApi.manager.hasDirtyForm(), false, 'Manager reflects clean state');
  assert.strictEqual(sandbox.window._listeners.has('beforeunload'), false, 'beforeunload handler removed');
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
