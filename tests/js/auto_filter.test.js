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
  constructor(options = {}) {
    this.elements = [];
    this._listeners = {};
    this.attributes = {};
    this.method = (options.method || 'get').toLowerCase();
    if (options.action) {
      this.attributes.action = options.action;
    }
  }

  addEventListener(type, handler) {
    if (!this._listeners[type]) {
      this._listeners[type] = [];
    }
    this._listeners[type].push(handler);
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

  getAttribute(name) {
    if (name === 'method') {
      return this.method;
    }
    return this.attributes[name] || null;
  }
}

function createContext() {
  const document = {
    readyState: 'complete',
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };
  const locationCalls = [];
  const window = {
    location: {
      href: 'https://example.com/',
      assign(url) {
        locationCalls.push(url);
        this.href = url;
      },
    },
    addEventListener() {},
    removeEventListener() {},
  };
  const sandbox = {
    window,
    document,
    console,
    setTimeout,
    clearTimeout,
    URL,
    URLSearchParams,
  };
  sandbox.globalThis = sandbox;
  sandbox.__locationCalls = locationCalls;
  return sandbox;
}

async function run() {
  const sandbox = createContext();
  const codePath = path.join(__dirname, '..', '..', 'app', 'static', 'js', 'auto_filter.js');
  const code = fs.readFileSync(codePath, 'utf8');
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);

  const autoFilter = sandbox.window.CBSAutoFilter;
  assert.ok(autoFilter, 'Auto filter API should be present');

  // Test immediate select change submits with preserved params.
  sandbox.window.location.href = 'https://example.com/users?page=2';
  sandbox.__locationCalls.length = 0;
  const selectField = new FakeField('region', '', { tagName: 'SELECT', type: 'select-one' });
  selectField.options = [
    { value: '', selected: true },
    { value: 'EU', selected: false },
  ];
  const selectForm = new FakeForm({ action: 'https://example.com/users', method: 'get' });
  selectForm.elements = [selectField];
  autoFilter.registerForm(selectForm, {});
  selectField.value = 'EU';
  selectField.options[0].selected = false;
  selectField.options[1].selected = true;
  selectField.dispatch('change');
  assert.strictEqual(sandbox.__locationCalls.length, 1, 'Select change triggers submit');
  assert.strictEqual(
    sandbox.__locationCalls[0],
    'https://example.com/users?page=2&region=EU',
    'Existing params preserved and new one added'
  );

  // Test debounced text input and clearing value.
  sandbox.window.location.href = 'https://example.com/materials?status=open';
  sandbox.__locationCalls.length = 0;
  const textField = new FakeField('q', '', { type: 'text', tagName: 'INPUT' });
  const textForm = new FakeForm({ action: 'https://example.com/materials', method: 'get' });
  textForm.elements = [textField];
  autoFilter.registerForm(textForm, { debounceMs: 50 });
  textField.value = 'kits';
  textField.dispatch('input');
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.strictEqual(sandbox.__locationCalls.length, 0, 'Debounce prevents early submit');
  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.strictEqual(sandbox.__locationCalls.length, 1, 'Debounce elapsed triggers submit');
  assert.strictEqual(
    sandbox.__locationCalls[0],
    'https://example.com/materials?status=open&q=kits',
    'Query appended alongside preserved params'
  );

  sandbox.__locationCalls.length = 0;
  textField.value = '';
  textField.dispatch('input');
  await new Promise((resolve) => setTimeout(resolve, 60));
  assert.strictEqual(
    sandbox.__locationCalls[0],
    'https://example.com/materials?status=open',
    'Clearing input removes parameter'
  );

  // Test pressing Enter submits immediately.
  sandbox.__locationCalls.length = 0;
  textField.value = 'rush';
  textField.dispatch('keydown', { key: 'Enter' });
  assert.strictEqual(sandbox.__locationCalls.length, 1, 'Enter key triggers immediate submit');
  assert.strictEqual(
    sandbox.__locationCalls[0],
    'https://example.com/materials?status=open&q=rush',
    'Enter submission sets current value'
  );
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
