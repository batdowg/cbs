const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

class FakeClassList {
  constructor() {
    this._set = new Set();
  }

  add(name) {
    this._set.add(name);
  }

  remove(name) {
    this._set.delete(name);
  }
}

class FakeElement {
  constructor() {
    this._listeners = {};
    this.classList = new FakeClassList();
  }

  addEventListener(type, handler) {
    if (!this._listeners[type]) {
      this._listeners[type] = [];
    }
    this._listeners[type].push(handler);
  }

  dispatchEvent(event) {
    let evt = event;
    if (!evt) {
      evt = {};
    }
    if (typeof evt === 'string') {
      evt = { type: evt };
    }
    if (!evt.type) {
      return evt;
    }
    if (!evt.preventDefault) {
      evt.preventDefault = () => {};
    }
    if (!evt.stopImmediatePropagation) {
      evt.stopImmediatePropagation = () => {};
    }
    if (!evt.target) {
      evt.target = this;
    }
    const handlers = this._listeners[evt.type] || [];
    handlers.forEach((handler) => handler(evt));
    return evt;
  }
}

class FakeOption {
  constructor(value, label) {
    this.value = value;
    this.textContent = label;
    this.selected = false;
  }
}

class FakeSelect extends FakeElement {
  constructor(id, options = []) {
    super();
    this.id = id;
    this.options = options;
    this.value = options.length ? options[0].value : '';
    this.dispatched = [];
  }

  appendChild(option) {
    this.options.push(option);
  }

  dispatchEvent(event) {
    const evt = super.dispatchEvent(event);
    if (evt && evt.type) {
      this.dispatched.push(evt.type);
    }
    return evt;
  }
}

class FakeField extends FakeElement {
  constructor(name, value, options = {}) {
    super();
    this.name = name;
    this.type = options.type || 'text';
    this.value = value || '';
    this.defaultValue = this.value;
    this.checked = Boolean(options.checked);
    this.defaultChecked = this.checked;
    this.options = options.options || [];
  }

  reset() {
    this.value = this.defaultValue;
    this.checked = this.defaultChecked;
  }
}

class FakeCheckboxField extends FakeField {
  constructor(name, value, checked) {
    super(name, value, { type: 'checkbox', checked });
  }
}

class FakeSelectField extends FakeField {
  constructor(name, value, options) {
    super(name, value, { type: 'select-one', options });
  }
}

class FakeErrorBlock extends FakeElement {
  constructor(name) {
    super();
    this.name = name;
    this.hidden = true;
    this.textContent = '';
  }

  getAttribute(attr) {
    if (attr === 'data-error-for') {
      return this.name;
    }
    return null;
  }
}

class FakeButton extends FakeElement {
  constructor() {
    super();
    this.attributes = {};
    this.previousElementSibling = null;
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name]
      : null;
  }
}

class FakeForm extends FakeElement {
  constructor(fields, errorBlocks) {
    super();
    this.fields = fields;
    this.errorBlocks = errorBlocks;
  }

  querySelector(selector) {
    if (selector === 'form[data-add-client-form]' || selector === 'form') {
      return this;
    }
    const nameMatch = selector.match(/\[name="([^"]+)"\]/);
    if (nameMatch) {
      return this.fields[nameMatch[1]] || null;
    }
    return null;
  }

  querySelectorAll(selector) {
    if (selector === '[data-error-for]') {
      return this.errorBlocks;
    }
    return [];
  }

  reset() {
    Object.values(this.fields).forEach((field) => {
      if (field && typeof field.reset === 'function') {
        field.reset();
      }
    });
  }
}

class FakeDialog extends FakeElement {
  constructor(form, cancelBtn) {
    super();
    this.form = form;
    this.cancelBtn = cancelBtn;
    this.isOpen = false;
  }

  querySelector(selector) {
    if (selector === 'form[data-add-client-form]' || selector === 'form') {
      return this.form;
    }
    if (selector === '[data-add-client-cancel]') {
      return this.cancelBtn;
    }
    return null;
  }

  showModal() {
    this.isOpen = true;
  }

  close() {
    this.isOpen = false;
  }
}

class FakeFormData {
  constructor(form) {
    this.map = new Map();
    Object.values(form.fields).forEach((field) => {
      if (!field) {
        return;
      }
      if (field.type === 'checkbox') {
        if (field.checked) {
          this.map.set(field.name, field.value);
        }
        return;
      }
      this.map.set(field.name, field.value);
    });
  }

  get(name) {
    return this.map.has(name) ? this.map.get(name) : null;
  }

  set(name, value) {
    this.map.set(name, value);
  }

  delete(name) {
    this.map.delete(name);
  }
}

class FakeDomEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.bubbles = Boolean(init.bubbles);
  }
}

function createSandbox() {
  const documentListeners = new Map();
  const document = {
    readyState: 'loading',
    addEventListener(type, handler) {
      if (!documentListeners.has(type)) {
        documentListeners.set(type, new Set());
      }
      documentListeners.get(type).add(handler);
    },
    removeEventListener(type, handler) {
      if (!documentListeners.has(type)) {
        return;
      }
      documentListeners.get(type).delete(handler);
      if (documentListeners.get(type).size === 0) {
        documentListeners.delete(type);
      }
    },
    dispatchEvent(event) {
      const handlers = documentListeners.get(event.type) || [];
      handlers.forEach((handler) => handler.call(document, event));
    },
  };
  const window = {
    document,
    addEventListener() {},
    removeEventListener() {},
    fetch: () => Promise.resolve({ status: 200, json: () => Promise.resolve({}) }),
    FormData: FakeFormData,
    Event: FakeDomEvent,
  };
  const sandbox = {
    window,
    document,
    console,
    setTimeout,
    clearTimeout,
    FormData: FakeFormData,
    Event: FakeDomEvent,
  };
  sandbox.globalThis = sandbox;
  return sandbox;
}

function buildFakeDocument() {
  const selects = [
    new FakeSelect('row-select', [new FakeOption('', '—'), new FakeOption('1', 'Alpha')]),
    new FakeSelect('other-select', [new FakeOption('', '—')]),
  ];
  const trigger = new FakeButton();
  trigger.setAttribute('data-target-select', 'row-select');
  trigger.previousElementSibling = selects[0];

  const errors = [
    new FakeErrorBlock('name'),
    new FakeErrorBlock('data_region'),
    new FakeErrorBlock('__all__'),
  ];

  const fields = {
    name: new FakeField('name', ''),
    data_region: new FakeSelectField('data_region', '', []),
    is_active: new FakeCheckboxField('is_active', '1', true),
  };
  const cancelBtn = new FakeButton();
  const form = new FakeForm(fields, errors);
  const dialog = new FakeDialog(form, cancelBtn);

  const doc = {
    readyState: 'complete',
    querySelector(selector) {
      if (selector === '[data-add-client-modal]') {
        return dialog;
      }
      return null;
    },
    querySelectorAll(selector) {
      if (selector === '[data-add-client-trigger]') {
        return [trigger];
      }
      if (selector === 'select[data-client-select]') {
        return selects;
      }
      return [];
    },
    getElementById(id) {
      return selects.find((select) => select.id === id) || null;
    },
    createElement(tag) {
      if (tag === 'option') {
        return new FakeOption('', '');
      }
      return null;
    },
  };

  return { document: doc, selects, trigger, form, dialog };
}

async function run() {
  const sandbox = createSandbox();
  const codePath = path.join(__dirname, '..', '..', 'app', 'static', 'js', 'add_client_modal.js');
  const code = fs.readFileSync(codePath, 'utf8');
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);

  const fetchCalls = [];
  sandbox.window.fetch = (url, options) => {
    fetchCalls.push({ url, options });
    return Promise.resolve({
      status: 200,
      json: () => Promise.resolve({ id: 99, name: 'New Client' }),
    });
  };

  const { document: fakeDocument, selects, trigger, form, dialog } = buildFakeDocument();
  const controller = sandbox.window.CBSAddClientModal.createController(fakeDocument);
  assert.ok(controller, 'Controller should initialize with fake document');

  trigger.dispatchEvent({ type: 'click', preventDefault() {} });
  assert.strictEqual(dialog.isOpen, true, 'Dialog opens on trigger');

  form.fields.name.value = 'New Client';
  form.fields.data_region.value = 'EU';
  form.fields.is_active.checked = true;

  form.dispatchEvent({ type: 'submit', preventDefault() {} });
  await new Promise((resolve) => setImmediate(resolve));

  assert.strictEqual(fetchCalls.length, 1, 'Fetch called once');
  const bodyData = fetchCalls[0].options.body;
  assert.strictEqual(bodyData.get('status'), 'active', 'Status set to active');
  assert.strictEqual(bodyData.get('is_active'), null, 'is_active removed before submit');

  const primaryOptions = selects[0].options.map((opt) => opt.value);
  const secondaryOptions = selects[1].options.map((opt) => opt.value);
  assert.ok(primaryOptions.includes('99'), 'Primary select includes new client');
  assert.ok(secondaryOptions.includes('99'), 'All selects refreshed with new client');
  assert.strictEqual(selects[0].value, '99', 'Active select points to new client');
  assert.ok(selects[0].dispatched.includes('change'), 'Change event dispatched for active select');
  assert.strictEqual(dialog.isOpen, false, 'Dialog closes after save');
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
