(function () {
  const DEFAULT_DEBOUNCE = 400;
  const TEXT_INPUT_TYPES = new Set([
    'text',
    'search',
    'email',
    'tel',
    'number',
    'url',
    'password',
  ]);

  function shouldDebounceInput(element) {
    const tag = (element.tagName || '').toLowerCase();
    if (tag === 'textarea') {
      return true;
    }
    const type = (element.type || '').toLowerCase();
    if (TEXT_INPUT_TYPES.has(type) || type === '') {
      return true;
    }
    return false;
  }

  function createURL(action) {
    if (typeof window === 'undefined') {
      return null;
    }
    const base = action || window.location.href;
    try {
      return new URL(base, window.location.href);
    } catch (err) {
      return null;
    }
  }

  class AutoFilterForm {
    constructor(form, options = {}) {
      this.form = form;
      this.debounceMs = options.debounceMs || DEFAULT_DEBOUNCE;
      this.timer = null;
      this.handleChange = this.handleChange.bind(this);
      this.handleInput = this.handleInput.bind(this);
      this.handleKeyDown = this.handleKeyDown.bind(this);
      this.handleSubmit = this.handleSubmit.bind(this);
      this.attach();
    }

    attach() {
      const elements = Array.from(this.form.elements || []);
      for (const el of elements) {
        if (!el || !el.name || el.disabled) {
          continue;
        }
        const tag = (el.tagName || '').toLowerCase();
        const type = (el.type || '').toLowerCase();
        if (tag === 'select' || type === 'checkbox' || type === 'radio') {
          el.addEventListener('change', this.handleChange);
        } else if (shouldDebounceInput(el)) {
          el.addEventListener('input', this.handleInput);
          el.addEventListener('change', this.handleChange);
          el.addEventListener('keydown', this.handleKeyDown);
        } else {
          el.addEventListener('change', this.handleChange);
        }
      }
      this.form.addEventListener('submit', this.handleSubmit);
    }

    handleSubmit(event) {
      if (event) {
        event.preventDefault();
      }
      this.submitNow();
    }

    handleChange() {
      this.submitNow();
    }

    handleInput() {
      this.scheduleSubmit();
    }

    handleKeyDown(event) {
      if (event && event.key === 'Enter') {
        event.preventDefault();
        this.submitNow();
      }
    }

    scheduleSubmit() {
      if (this.timer) {
        clearTimeout(this.timer);
      }
      this.timer = setTimeout(() => {
        this.timer = null;
        this.submitNow();
      }, this.debounceMs);
    }

    submitNow() {
      if (this.timer) {
        clearTimeout(this.timer);
        this.timer = null;
      }
      const targetUrl = this.buildTargetUrl();
      if (!targetUrl || typeof window === 'undefined') {
        return;
      }
      const current = window.location ? window.location.href : null;
      if (current === targetUrl) {
        return;
      }
      if (window.location && typeof window.location.assign === 'function') {
        window.location.assign(targetUrl);
      } else if (window.location) {
        window.location.href = targetUrl;
      }
    }

    buildTargetUrl() {
      if (typeof window === 'undefined') {
        return null;
      }
      const currentUrl = createURL(window.location.href);
      if (!currentUrl) {
        return null;
      }
      const actionAttr = this.form.getAttribute('action');
      const baseUrl = createURL(actionAttr || currentUrl.pathname);
      if (!baseUrl) {
        return null;
      }
      const params = new URLSearchParams(currentUrl.search);
      const elements = Array.from(this.form.elements || []).filter((el) => el && el.name && !el.disabled);
      const names = new Set(elements.map((el) => el.name));
      for (const name of names) {
        params.delete(name);
      }
      const grouped = new Map();
      for (const el of elements) {
        const name = el.name;
        const tag = (el.tagName || '').toLowerCase();
        const type = (el.type || '').toLowerCase();
        if (type === 'checkbox' || type === 'radio') {
          if (!el.checked) {
            continue;
          }
          this.addGroupedValue(grouped, name, el.value ?? 'on');
          continue;
        }
        if (tag === 'select' && el.multiple) {
          const options = Array.from(el.options || []);
          let added = false;
          for (const option of options) {
            if (option.selected && option.value !== '') {
              this.addGroupedValue(grouped, name, option.value);
              added = true;
            }
          }
          if (!added) {
            // No selection means clearing the parameter.
          }
          continue;
        }
        const value = el.value ?? '';
        if (value === '') {
          continue;
        }
        this.addGroupedValue(grouped, name, value);
      }
      for (const [name, values] of grouped.entries()) {
        if (!values.length) {
          continue;
        }
        params.delete(name);
        for (const value of values) {
          params.append(name, value);
        }
      }
      const serialized = params.toString();
      baseUrl.search = serialized ? `?${serialized}` : '';
      return baseUrl.toString();
    }

    addGroupedValue(grouped, name, value) {
      if (!grouped.has(name)) {
        grouped.set(name, []);
      }
      grouped.get(name).push(value);
    }
  }

  class AutoFilterManager {
    constructor() {
      this.instances = new Set();
    }

    register(form, options) {
      const instance = new AutoFilterForm(form, options);
      this.instances.add(instance);
      return instance;
    }

    initFromDocument() {
      if (typeof document === 'undefined') {
        return;
      }
      const forms = document.querySelectorAll('form[data-autofilter="true"][method="get" i]');
      forms.forEach((form) => {
        this.register(form, {});
      });
    }
  }

  const manager = new AutoFilterManager();

  const api = {
    manager,
    AutoFilterForm,
    registerForm(form, options) {
      return manager.register(form, options);
    },
    init() {
      manager.initFromDocument();
    },
  };

  if (typeof window !== 'undefined') {
    window.CBSAutoFilter = api;
    if (typeof document !== 'undefined') {
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => manager.initFromDocument());
      } else {
        manager.initFromDocument();
      }
    }
  }
})();
