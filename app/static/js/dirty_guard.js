(function () {
  const CONFIRM_MESSAGE = 'You have unsaved changes. Leave without saving?';

  function serializeForm(form) {
    const pairs = [];
    const elements = Array.from(form.elements || []);
    for (const el of elements) {
      if (!el || !el.name || el.disabled) {
        continue;
      }
      const name = el.name;
      const type = (el.type || '').toLowerCase();
      if (type === 'checkbox' || type === 'radio') {
        if (!el.checked) {
          continue;
        }
        pairs.push([name, el.value ?? 'on']);
        continue;
      }
      if (type === 'select-multiple') {
        const options = Array.from(el.options || []);
        for (const option of options) {
          if (option.selected) {
            pairs.push([name, option.value]);
          }
        }
        continue;
      }
      pairs.push([name, el.value ?? '']);
    }
    pairs.sort((a, b) => {
      if (a[0] === b[0]) {
        return a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0;
      }
      return a[0] < b[0] ? -1 : 1;
    });
    return JSON.stringify(pairs);
  }

  class DirtyForm {
    constructor(form, options = {}) {
      this.form = form;
      this.serialize = options.serialize || (() => serializeForm(this.form));
      this.onDirtyChange = options.onDirtyChange || function () {};
      this.isSubmitting = false;
      this.isDirty = false;
      this.initialState = this.serialize();
      this.handleMutation = this.handleMutation.bind(this);
      this.handleSubmit = this.handleSubmit.bind(this);
      this.handleReset = this.handleReset.bind(this);
      form.addEventListener('input', this.handleMutation, true);
      form.addEventListener('change', this.handleMutation, true);
      form.addEventListener('submit', this.handleSubmit);
      form.addEventListener('reset', this.handleReset);
    }

    checkDirty() {
      const current = this.serialize();
      const isDirty = current !== this.initialState;
      if (isDirty !== this.isDirty) {
        this.isDirty = isDirty;
        this.onDirtyChange(isDirty, this);
      }
      return this.isDirty;
    }

    handleMutation() {
      if (this.isSubmitting) {
        return;
      }
      this.checkDirty();
    }

    handleSubmit() {
      this.isSubmitting = true;
      this.markClean();
      // Delay resetting submitting flag to allow navigation flow to finish.
      setTimeout(() => {
        this.isSubmitting = false;
      }, 0);
    }

    handleReset() {
      setTimeout(() => {
        this.markClean();
      }, 0);
    }

    markClean() {
      this.initialState = this.serialize();
      if (this.isDirty) {
        this.isDirty = false;
        this.onDirtyChange(false, this);
      }
    }
  }

  class DirtyGuardManager {
    constructor() {
      this.instances = new Map();
      this.suppressPrompt = false;
      this.beforeUnloadHandler = (event) => {
        if (this.shouldPrompt()) {
          event.preventDefault();
          event.returnValue = '';
          return '';
        }
        return undefined;
      };
      this.handleDocumentClick = this.handleDocumentClick.bind(this);
      this.handleBypassSubmit = this.handleBypassSubmit.bind(this);
      if (typeof document !== 'undefined') {
        document.addEventListener('click', this.handleDocumentClick, true);
        document.addEventListener('submit', this.handleBypassSubmit, true);
      }
    }

    register(form, options) {
      if (this.instances.has(form)) {
        return this.instances.get(form);
      }
      const tracked = new DirtyForm(form, {
        ...options,
        onDirtyChange: () => {
          this.updateBeforeUnload();
        },
      });
      this.instances.set(form, tracked);
      this.updateBeforeUnload();
      return tracked;
    }

    unregister(form) {
      if (!this.instances.has(form)) {
        return;
      }
      const instance = this.instances.get(form);
      form.removeEventListener('input', instance.handleMutation, true);
      form.removeEventListener('change', instance.handleMutation, true);
      form.removeEventListener('submit', instance.handleSubmit);
      form.removeEventListener('reset', instance.handleReset);
      this.instances.delete(form);
      this.updateBeforeUnload();
    }

    hasDirtyForm() {
      for (const instance of this.instances.values()) {
        if (instance.isDirty && !instance.isSubmitting) {
          return true;
        }
      }
      return false;
    }

    shouldPrompt() {
      if (this.suppressPrompt) {
        return false;
      }
      return this.hasDirtyForm();
    }

    updateBeforeUnload() {
      if (typeof window === 'undefined') {
        return;
      }
      if (this.shouldPrompt()) {
        window.addEventListener('beforeunload', this.beforeUnloadHandler);
      } else {
        window.removeEventListener('beforeunload', this.beforeUnloadHandler);
      }
    }

    confirmNavigation() {
      if (!this.shouldPrompt()) {
        return true;
      }
      const confirmFn = (typeof window !== 'undefined' && window.confirm) || (() => true);
      const ok = !!confirmFn(CONFIRM_MESSAGE);
      if (ok) {
        this.suppressNextPrompt();
      }
      return ok;
    }

    suppressNextPrompt() {
      this.suppressPrompt = true;
      setTimeout(() => {
        this.suppressPrompt = false;
      }, 0);
    }

    handleDocumentClick(event) {
      const target = event.target;
      if (!target) {
        return;
      }
      const bypassEl = this.findClosestAttr(target, 'data-dirty-guard-bypass');
      if (bypassEl) {
        this.suppressNextPrompt();
        return;
      }
      const anchor = this.findClosestAnchor(target);
      if (!anchor) {
        return;
      }
      if (anchor.target && anchor.target.toLowerCase() === '_blank') {
        return;
      }
      const href = anchor.getAttribute('href');
      if (!href || href.startsWith('#')) {
        return;
      }
      if (!this.shouldPrompt()) {
        return;
      }
      const ok = this.confirmNavigation();
      if (!ok) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }

    handleBypassSubmit(event) {
      const target = event.target;
      if (!target) {
        return;
      }
      if (
        typeof HTMLFormElement !== 'undefined' &&
        target instanceof HTMLFormElement &&
        target.hasAttribute('data-dirty-guard-bypass')
      ) {
        this.suppressNextPrompt();
      }
    }

    findClosestAnchor(start) {
      let el = start;
      while (el && el !== document) {
        if (typeof el.tagName === 'string' && el.tagName.toLowerCase() === 'a' && el.hasAttribute('href')) {
          return el;
        }
        el = el.parentNode || el.parentElement;
      }
      return null;
    }

    findClosestAttr(start, attr) {
      let el = start;
      while (el && el !== document) {
        if (el.hasAttribute && el.hasAttribute(attr)) {
          return el;
        }
        el = el.parentNode || el.parentElement;
      }
      return null;
    }

    initFromDocument() {
      if (typeof document === 'undefined') {
        return;
      }
      const forms = document.querySelectorAll('form[data-dirty-guard="true"]');
      forms.forEach((form) => this.register(form));
    }
  }

  const manager = new DirtyGuardManager();

  const api = {
    manager,
    DirtyForm,
    registerForm(form, options) {
      return manager.register(form, options);
    },
    init() {
      manager.initFromDocument();
    },
  };

  if (typeof window !== 'undefined') {
    window.CBSDirtyGuard = api;
    if (typeof document !== 'undefined') {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => manager.initFromDocument());
      } else {
        manager.initFromDocument();
      }
    }
  }
})();
