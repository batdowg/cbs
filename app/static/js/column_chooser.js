(function () {
  'use strict';

  var cssEscape = window.CSS && window.CSS.escape
    ? window.CSS.escape.bind(window.CSS)
    : function (value) {
        return String(value).replace(/[\s!"#$%&'()*+,./:;<=>?@[\\\]^`{|}~]/g, '\\$&');
      };

  var MIN_COLUMN_WIDTH = 80;

  function storageAvailable() {
    try {
      var testKey = '__cbs__';
      window.localStorage.setItem(testKey, testKey);
      window.localStorage.removeItem(testKey);
      return true;
    } catch (err) {
      return false;
    }
  }

  var canUseStorage = storageAvailable();

  function TableColumnChooser(container) {
    this.container = container;
    this.table = container.querySelector('table');
    this.toggleButton = container.querySelector('[data-column-chooser-toggle]');
    if (!this.table || !this.toggleButton) {
      return;
    }

    this.panelId = 'column-chooser-' + Math.random().toString(36).slice(2, 9);
    this.label = container.getAttribute('data-chooser-label') || 'Choose columns';
    this.storageKey = container.getAttribute('data-storage-key') || '';
    this.widthStorageKey =
      container.getAttribute('data-width-storage-key') || '';

    this.columns = this.collectColumns();
    if (!this.columns.length) {
      return;
    }

    this.requiredKeys = this.columns
      .filter(function (col) {
        return col.required;
      })
      .map(function (col) {
        return col.key;
      });
    this.optionalKeys = this.columns
      .filter(function (col) {
        return !col.required;
      })
      .map(function (col) {
        return col.key;
      });
    this.optionalDefaultOrder = this.optionalKeys.slice();
    this.defaultHidden = new Set(
      this.columns
        .filter(function (col) {
          return !col.required && col.defaultHidden;
        })
        .map(function (col) {
          return col.key;
        })
    );

    this.state = this.loadState();
    this.widthState = this.loadWidths();
    this.controlMap = new Map();
    this.draggedItem = null;
    this.draggedKey = null;
    this.isResizing = false;
    this.resizingKey = null;
    this.resizingWidth = null;
    this.resizeStartX = 0;
    this.resizeStartWidth = 0;
    this.resizeMinWidth = MIN_COLUMN_WIDTH;
    this.boundHandleMouseMove = null;
    this.boundHandleMouseUp = null;
    this.previousBodyCursor = '';
    this.previousBodyUserSelect = '';

    this.buildPanel();
    this.syncListToState(this.state);
    this.applyState(this.state);
    this.initResizeHandles();
    this.bindEvents();
    container.dataset.columnChooserInitialized = 'true';
  }

  TableColumnChooser.prototype.collectColumns = function () {
    var headerRow = this.table.querySelector('thead tr');
    if (!headerRow) {
      return [];
    }
    var headers = headerRow.querySelectorAll('[data-column-key]');
    var columns = [];
    headers.forEach(function (th) {
      var key = th.getAttribute('data-column-key');
      if (!key) {
        return;
      }
      columns.push({
        key: key,
        label: th.getAttribute('data-column-label') || th.textContent.trim(),
        required: th.getAttribute('data-column-required') === 'true',
        defaultHidden: th.getAttribute('data-column-default-hidden') === 'true',
      });
    });
    return columns;
  };

  TableColumnChooser.prototype.loadState = function () {
    var state = {
      order: [],
      hidden: new Set(this.defaultHidden),
    };
    if (!canUseStorage || !this.storageKey) {
      return state;
    }
    try {
      var raw = window.localStorage.getItem(this.storageKey);
      if (!raw) {
        return state;
      }
      var data = JSON.parse(raw);
      if (Array.isArray(data.order)) {
        state.order = data.order.filter(
          function (key) {
            return this.optionalKeys.indexOf(key) !== -1;
          }.bind(this)
        );
      }
      if (Array.isArray(data.hidden)) {
        state.hidden = new Set(
          data.hidden.filter(
            function (key) {
              return this.optionalKeys.indexOf(key) !== -1;
            }.bind(this)
          )
        );
      }
    } catch (err) {
      // ignore malformed storage
    }
    return state;
  };

  TableColumnChooser.prototype.loadWidths = function () {
    var widths = Object.create(null);
    if (!canUseStorage || !this.widthStorageKey) {
      return widths;
    }
    try {
      var raw = window.localStorage.getItem(this.widthStorageKey);
      if (!raw) {
        return widths;
      }
      var data = JSON.parse(raw);
      if (data && typeof data === 'object') {
        this.columns.forEach(
          function (col) {
            var value = data[col.key];
            if (value === undefined || value === null) {
              return;
            }
            var numeric = Number(value);
            if (isFinite(numeric) && numeric > 0) {
              widths[col.key] = numeric;
            }
          }.bind(this)
        );
      }
    } catch (err) {
      // ignore malformed storage
    }
    return widths;
  };

  TableColumnChooser.prototype.saveState = function () {
    if (!canUseStorage || !this.storageKey) {
      return;
    }
    var payload = {
      order: this.state.order.filter(
        function (key) {
          return this.optionalKeys.indexOf(key) !== -1;
        }.bind(this)
      ),
      hidden: Array.from(this.state.hidden),
    };
    try {
      window.localStorage.setItem(this.storageKey, JSON.stringify(payload));
    } catch (err) {
      // storage full or unavailable; ignore
    }
  };

  TableColumnChooser.prototype.saveWidths = function () {
    if (!canUseStorage || !this.widthStorageKey) {
      return;
    }
    var payload = {};
    var hasValues = false;
    if (!this.widthState) {
      this.widthState = Object.create(null);
    }
    Object.keys(this.widthState).forEach(
      function (key) {
        var value = this.widthState[key];
        if (typeof value === 'number' && isFinite(value) && value > 0) {
          payload[key] = Math.round(value);
          hasValues = true;
        }
      }.bind(this)
    );
    try {
      if (hasValues) {
        window.localStorage.setItem(
          this.widthStorageKey,
          JSON.stringify(payload)
        );
      } else {
        window.localStorage.removeItem(this.widthStorageKey);
      }
    } catch (err) {
      // storage full or unavailable; ignore
    }
  };

  TableColumnChooser.prototype.effectiveOptionalOrder = function (orderOverride) {
    var result = [];
    if (Array.isArray(orderOverride)) {
      orderOverride.forEach(
        function (key) {
          if (this.optionalKeys.indexOf(key) !== -1 && result.indexOf(key) === -1) {
            result.push(key);
          }
        }.bind(this)
      );
    }
    this.optionalDefaultOrder.forEach(function (key) {
      if (result.indexOf(key) === -1) {
        result.push(key);
      }
    });
    return result;
  };

  TableColumnChooser.prototype.applyState = function (state) {
    var optionalOrder = this.effectiveOptionalOrder(state.order);
    this.currentOptionalOrder = optionalOrder;
    var finalOrder = this.requiredKeys.concat(optionalOrder);
    this.reorderTable(finalOrder);
    this.columns.forEach(
      function (col) {
        var visible = col.required || !state.hidden.has(col.key);
        this.setColumnVisibility(col.key, visible);
      }.bind(this)
    );
    this.applyWidths();
    this.updateControlStates();
  };

  TableColumnChooser.prototype.reorderTable = function (order) {
    var headerRow = this.table.querySelector('thead tr');
    if (headerRow) {
      var headerFragment = document.createDocumentFragment();
      order.forEach(function (key) {
        var cell = headerRow.querySelector('[data-column-key="' + cssEscape(key) + '"]');
        if (cell) {
          headerFragment.appendChild(cell);
        }
      });
      headerRow.appendChild(headerFragment);
    }
    var bodyRows = this.table.querySelectorAll('tbody tr');
    bodyRows.forEach(function (row) {
      var fragment = document.createDocumentFragment();
      order.forEach(function (key) {
        var cell = row.querySelector('[data-column-key="' + cssEscape(key) + '"]');
        if (cell) {
          fragment.appendChild(cell);
        }
      });
      row.appendChild(fragment);
    });
  };

  TableColumnChooser.prototype.setColumnVisibility = function (key, visible) {
    var selector = '[data-column-key="' + cssEscape(key) + '"]';
    this.table.querySelectorAll(selector).forEach(
      function (cell) {
        if (visible) {
          cell.removeAttribute('data-column-hidden');
          if (cell.tagName === 'TH') {
            if (cell.dataset.originalAriaSort) {
              cell.setAttribute('aria-sort', cell.dataset.originalAriaSort);
              delete cell.dataset.originalAriaSort;
            }
            if (cell.dataset.originalSortClasses) {
              cell.dataset.originalSortClasses.split(' ').forEach(function (cls) {
                if (cls) {
                  cell.classList.add(cls);
                }
              });
              delete cell.dataset.originalSortClasses;
            }
          }
        } else {
          cell.setAttribute('data-column-hidden', 'true');
          if (cell.tagName === 'TH') {
            if (!cell.dataset.originalAriaSort && cell.hasAttribute('aria-sort')) {
              cell.dataset.originalAriaSort = cell.getAttribute('aria-sort');
            }
            cell.removeAttribute('aria-sort');
            if (!cell.dataset.originalSortClasses) {
              var classes = (cell.className || '').split(/\s+/);
              var stored = classes.filter(function (cls) {
                return cls && cls.toLowerCase().indexOf('sort') !== -1;
              });
              if (stored.length) {
                cell.dataset.originalSortClasses = stored.join(' ');
              }
            }
            if (cell.dataset.originalSortClasses) {
              cell.dataset.originalSortClasses.split(' ').forEach(function (cls) {
                if (cls) {
                  cell.classList.remove(cls);
                }
              });
            }
          }
        }
      }
    );
  };

  TableColumnChooser.prototype.applyWidths = function () {
    if (!this.table) {
      return;
    }
    if (!this.widthState) {
      this.widthState = Object.create(null);
    }
    var self = this;
    this.columns.forEach(function (col) {
      self.applyWidth(col.key, self.widthState[col.key]);
    });
  };

  TableColumnChooser.prototype.applyWidth = function (key, width) {
    var selector = '[data-column-key="' + cssEscape(key) + '"]';
    this.table.querySelectorAll(selector).forEach(function (cell) {
      if (typeof width === 'number' && isFinite(width) && width > 0) {
        var px = Math.round(width);
        cell.style.width = px + 'px';
        cell.style.minWidth = px + 'px';
        cell.style.maxWidth = px + 'px';
      } else {
        cell.style.width = '';
        cell.style.minWidth = '';
        cell.style.maxWidth = '';
      }
    });
  };

  TableColumnChooser.prototype.setStoredWidth = function (key, width) {
    if (!this.widthState) {
      this.widthState = Object.create(null);
    }
    if (typeof width === 'number' && isFinite(width) && width > 0) {
      this.widthState[key] = Math.round(width);
    } else {
      delete this.widthState[key];
    }
    this.saveWidths();
  };

  TableColumnChooser.prototype.buildPanel = function () {
    var panel = document.createElement('div');
    panel.className = 'column-chooser-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', this.label);
    panel.id = this.panelId;
    panel.hidden = true;

    var header = document.createElement('div');
    header.className = 'column-chooser__header';
    var title = document.createElement('h2');
    title.className = 'column-chooser__title';
    title.textContent = this.label;
    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'column-chooser__close btn btn-secondary btn-sm';
    closeBtn.textContent = 'Close';
    closeBtn.addEventListener(
      'click',
      function () {
        this.close();
      }.bind(this)
    );
    header.appendChild(title);
    header.appendChild(closeBtn);
    panel.appendChild(header);

    var hint = document.createElement('p');
    hint.className = 'column-chooser__hint';
    hint.textContent = 'Select columns to show or hide. Drag optional columns to change their order.';
    panel.appendChild(hint);

    var list = document.createElement('ul');
    list.className = 'column-chooser__list';
    panel.appendChild(list);
    this.list = list;

    this.columns.forEach(
      function (col) {
        var item = this.createListItem(col);
        list.appendChild(item);
      }.bind(this)
    );

    var footer = document.createElement('div');
    footer.className = 'column-chooser__footer';
    var resetBtn = document.createElement('button');
    resetBtn.type = 'button';
    resetBtn.className = 'column-chooser__reset btn btn-link';
    resetBtn.textContent = 'Reset to defaults';
    resetBtn.addEventListener(
      'click',
      function () {
        this.reset();
      }.bind(this)
    );
    footer.appendChild(resetBtn);
    panel.appendChild(footer);

    this.panel = panel;
    this.toggleButton.setAttribute('aria-controls', this.panelId);
    var toolbar = this.container.querySelector('.table-toolbar');
    if (toolbar) {
      toolbar.appendChild(panel);
    } else {
      this.container.insertBefore(panel, this.container.querySelector('.kt-table-wrapper'));
    }
  };

  TableColumnChooser.prototype.createListItem = function (col) {
    var item = document.createElement('li');
    item.className = 'column-chooser__item';
    item.setAttribute('data-column-key', col.key);
    if (col.required) {
      item.setAttribute('data-required', 'true');
    }

    var drag = document.createElement('span');
    drag.className = 'column-chooser__drag';
    drag.setAttribute('aria-hidden', 'true');
    drag.textContent = '≡';
    item.appendChild(drag);

    var checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = this.panelId + '-' + col.key;
    checkbox.className = 'column-chooser__check';
    checkbox.checked = true;
    if (col.required) {
      checkbox.disabled = true;
      checkbox.setAttribute('disabled', 'disabled');
    }
    checkbox.addEventListener(
      'change',
      function (event) {
        this.onCheckboxChange(col, event.target.checked);
      }.bind(this)
    );

    var label = document.createElement('label');
    label.className = 'column-chooser__label';
    label.setAttribute('for', checkbox.id);
    label.textContent = col.label;

    item.appendChild(checkbox);
    item.appendChild(label);

    var moveUp = null;
    var moveDown = null;

    if (!col.required) {
      item.setAttribute('draggable', 'true');
      item.addEventListener(
        'dragstart',
        function (event) {
          this.onDragStart(event, item, col.key);
        }.bind(this)
      );
      item.addEventListener(
        'dragover',
        function (event) {
          this.onDragOver(event, item);
        }.bind(this)
      );
      item.addEventListener(
        'dragleave',
        function () {
          item.classList.remove('is-drag-over');
        }
      );
      item.addEventListener(
        'drop',
        function (event) {
          this.onDrop(event, item);
        }.bind(this)
      );
      item.addEventListener(
        'dragend',
        function () {
          this.onDragEnd();
        }.bind(this)
      );

      var moveWrapper = document.createElement('div');
      moveWrapper.className = 'column-chooser__moves';

      moveUp = document.createElement('button');
      moveUp.type = 'button';
      moveUp.className = 'column-chooser__move';
      moveUp.setAttribute('aria-label', 'Move ' + col.label + ' left');
      moveUp.innerHTML = '<span aria-hidden="true">←</span>';
      moveUp.addEventListener(
        'click',
        function () {
          this.moveColumn(col.key, -1);
        }.bind(this)
      );

      moveDown = document.createElement('button');
      moveDown.type = 'button';
      moveDown.className = 'column-chooser__move';
      moveDown.setAttribute('aria-label', 'Move ' + col.label + ' right');
      moveDown.innerHTML = '<span aria-hidden="true">→</span>';
      moveDown.addEventListener(
        'click',
        function () {
          this.moveColumn(col.key, 1);
        }.bind(this)
      );

      moveWrapper.appendChild(moveUp);
      moveWrapper.appendChild(moveDown);
      item.appendChild(moveWrapper);
    }

    this.controlMap.set(col.key, {
      checkbox: checkbox,
      item: item,
      moveUp: moveUp,
      moveDown: moveDown,
      required: col.required,
    });

    return item;
  };

  TableColumnChooser.prototype.onCheckboxChange = function (col, visible) {
    if (col.required) {
      return;
    }
    if (!visible) {
      this.state.hidden.add(col.key);
    } else {
      this.state.hidden.delete(col.key);
    }
    this.applyState(this.state);
    this.saveState();
  };

  TableColumnChooser.prototype.onDragStart = function (event, item, key) {
    this.draggedItem = item;
    this.draggedKey = key;
    item.classList.add('is-dragging');
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', key);
    }
  };

  TableColumnChooser.prototype.onDragOver = function (event, item) {
    if (!this.draggedItem || item === this.draggedItem || item.dataset.required) {
      return;
    }
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
    item.classList.add('is-drag-over');
  };

  TableColumnChooser.prototype.onDrop = function (event, item) {
    if (!this.draggedItem || item === this.draggedItem || item.dataset.required) {
      return;
    }
    event.preventDefault();
    item.classList.remove('is-drag-over');
    var optionalItems = Array.from(this.list.children).filter(function (el) {
      return !el.dataset.required;
    });
    var draggedIndex = optionalItems.indexOf(this.draggedItem);
    var targetIndex = optionalItems.indexOf(item);
    if (draggedIndex === -1 || targetIndex === -1) {
      return;
    }
    if (draggedIndex < targetIndex) {
      this.list.insertBefore(this.draggedItem, item.nextSibling);
    } else {
      this.list.insertBefore(this.draggedItem, item);
    }
    this.updateStateFromList();
  };

  TableColumnChooser.prototype.onDragEnd = function () {
    if (this.draggedItem) {
      this.draggedItem.classList.remove('is-dragging');
    }
    this.draggedItem = null;
    this.draggedKey = null;
    this.list.querySelectorAll('.is-drag-over').forEach(function (el) {
      el.classList.remove('is-drag-over');
    });
  };

  TableColumnChooser.prototype.updateStateFromList = function () {
    var order = Array.from(this.list.children)
      .filter(function (el) {
        return !el.dataset.required;
      })
      .map(function (el) {
        return el.getAttribute('data-column-key');
      });
    this.state.order = order;
    this.applyState(this.state);
    this.saveState();
  };

  TableColumnChooser.prototype.moveColumn = function (key, delta) {
    var optionalOrder = this.effectiveOptionalOrder(this.state.order);
    var index = optionalOrder.indexOf(key);
    if (index === -1) {
      return;
    }
    var newIndex = index + delta;
    if (newIndex < 0 || newIndex >= optionalOrder.length) {
      return;
    }
    optionalOrder.splice(index, 1);
    optionalOrder.splice(newIndex, 0, key);
    this.state.order = optionalOrder.filter(
      function (colKey) {
        return this.optionalKeys.indexOf(colKey) !== -1;
      }.bind(this)
    );
    this.syncListToState(this.state);
    this.applyState(this.state);
    this.saveState();
  };

  TableColumnChooser.prototype.updateControlStates = function () {
    var hidden = this.state.hidden;
    var optionalOrder = this.effectiveOptionalOrder(this.state.order);
    var firstOptional = optionalOrder[0];
    var lastOptional = optionalOrder[optionalOrder.length - 1];
    this.controlMap.forEach(function (control, key) {
      var visible = control.required || !hidden.has(key);
      control.checkbox.checked = visible;
      if (control.moveUp) {
        control.moveUp.disabled = key === firstOptional || optionalOrder.length <= 1;
      }
      if (control.moveDown) {
        control.moveDown.disabled = key === lastOptional || optionalOrder.length <= 1;
      }
    });
  };

  TableColumnChooser.prototype.syncListToState = function (state) {
    if (!this.list) {
      return;
    }
    var itemsByKey = new Map();
    Array.from(this.list.children).forEach(function (item) {
      itemsByKey.set(item.getAttribute('data-column-key'), item);
    });
    var order = this.requiredKeys.concat(this.effectiveOptionalOrder(state.order));
    var fragment = document.createDocumentFragment();
    order.forEach(function (key) {
      var item = itemsByKey.get(key);
      if (item) {
        fragment.appendChild(item);
      }
    });
    this.list.appendChild(fragment);
  };

  TableColumnChooser.prototype.initResizeHandles = function () {
    if (!this.table) {
      return;
    }
    var headerRow = this.table.querySelector('thead tr');
    if (!headerRow) {
      return;
    }
    var self = this;
    headerRow.querySelectorAll('[data-column-key]').forEach(function (th) {
      var key = th.getAttribute('data-column-key');
      if (!key) {
        return;
      }
      if (th.getAttribute('data-column-resize-disabled') === 'true') {
        th.dataset.resizeHandleInitialized = 'true';
        return;
      }
      if (th.dataset.resizeHandleInitialized === 'true') {
        return;
      }
      th.dataset.resizeHandleInitialized = 'true';
      if (!th.style.position) {
        th.style.position = 'relative';
      }
      var handle = document.createElement('span');
      handle.className = 'column-resize-handle';
      handle.setAttribute('aria-hidden', 'true');
      handle.addEventListener(
        'mousedown',
        function (event) {
          self.startColumnResize(event, key);
        }
      );
      th.appendChild(handle);
    });
  };

  TableColumnChooser.prototype.startColumnResize = function (event, key) {
    if (this.isResizing) {
      return;
    }
    if (event.button !== undefined && event.button !== 0) {
      return;
    }
    var headerSelector = 'thead [data-column-key="' + cssEscape(key) + '"]';
    var headerCell = this.table.querySelector(headerSelector);
    if (!headerCell) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    this.isResizing = true;
    this.resizingKey = key;
    this.resizeStartX = event.clientX;
    this.resizeStartWidth = headerCell.offsetWidth;
    this.resizingWidth = Math.round(this.resizeStartWidth);
    var minAttr = headerCell.getAttribute('data-column-min-width');
    var minWidth = parseInt(minAttr, 10);
    if (!isFinite(minWidth) || minWidth <= 0) {
      minWidth = MIN_COLUMN_WIDTH;
    }
    this.resizeMinWidth = minWidth;
    this.previousBodyCursor = document.body.style.cursor || '';
    this.previousBodyUserSelect = document.body.style.userSelect || '';
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    this.container.classList.add('is-resizing');
    this.boundHandleMouseMove = this.onColumnResize.bind(this);
    this.boundHandleMouseUp = this.stopColumnResize.bind(this);
    document.addEventListener('mousemove', this.boundHandleMouseMove);
    document.addEventListener('mouseup', this.boundHandleMouseUp);
    window.addEventListener('blur', this.boundHandleMouseUp);
  };

  TableColumnChooser.prototype.onColumnResize = function (event) {
    if (!this.isResizing || !this.resizingKey) {
      return;
    }
    event.preventDefault();
    var delta = event.clientX - this.resizeStartX;
    var width = this.resizeStartWidth + delta;
    if (width < this.resizeMinWidth) {
      width = this.resizeMinWidth;
    }
    this.resizingWidth = Math.round(width);
    this.applyWidth(this.resizingKey, this.resizingWidth);
  };

  TableColumnChooser.prototype.stopColumnResize = function (event) {
    if (event && typeof event.preventDefault === 'function') {
      event.preventDefault();
    }
    if (!this.isResizing) {
      return;
    }
    if (this.boundHandleMouseMove) {
      document.removeEventListener('mousemove', this.boundHandleMouseMove);
    }
    if (this.boundHandleMouseUp) {
      document.removeEventListener('mouseup', this.boundHandleMouseUp);
      window.removeEventListener('blur', this.boundHandleMouseUp);
    }
    this.boundHandleMouseMove = null;
    this.boundHandleMouseUp = null;
    this.container.classList.remove('is-resizing');
    document.body.style.cursor = this.previousBodyCursor || '';
    document.body.style.userSelect = this.previousBodyUserSelect || '';
    this.previousBodyCursor = '';
    this.previousBodyUserSelect = '';
    if (this.resizingKey) {
      this.setStoredWidth(this.resizingKey, this.resizingWidth);
    }
    this.isResizing = false;
    this.resizingKey = null;
    this.resizingWidth = null;
    this.resizeStartX = 0;
    this.resizeStartWidth = 0;
  };

  TableColumnChooser.prototype.open = function () {
    if (!this.panel.hidden) {
      return;
    }
    this.previousFocus = document.activeElement;
    this.panel.hidden = false;
    this.toggleButton.setAttribute('aria-expanded', 'true');
    var focusTarget = this.panel.querySelector('input:not([disabled])') || this.panel.querySelector('button');
    if (focusTarget) {
      focusTarget.focus();
    }
    document.addEventListener('click', this.boundDocumentClick, true);
    document.addEventListener('keydown', this.boundKeydown, true);
  };

  TableColumnChooser.prototype.close = function () {
    if (this.panel.hidden) {
      return;
    }
    this.panel.hidden = true;
    this.toggleButton.setAttribute('aria-expanded', 'false');
    document.removeEventListener('click', this.boundDocumentClick, true);
    document.removeEventListener('keydown', this.boundKeydown, true);
    if (this.previousFocus && typeof this.previousFocus.focus === 'function') {
      this.previousFocus.focus();
    } else {
      this.toggleButton.focus();
    }
  };

  TableColumnChooser.prototype.toggle = function () {
    if (this.panel.hidden) {
      this.open();
    } else {
      this.close();
    }
  };

  TableColumnChooser.prototype.reset = function () {
    this.stopColumnResize();
    if (canUseStorage && this.storageKey) {
      try {
        window.localStorage.removeItem(this.storageKey);
      } catch (err) {
        // ignore
      }
    }
    if (canUseStorage && this.widthStorageKey) {
      try {
        window.localStorage.removeItem(this.widthStorageKey);
      } catch (err) {
        // ignore
      }
    }
    this.state = {
      order: [],
      hidden: new Set(this.defaultHidden),
    };
    this.widthState = Object.create(null);
    this.syncListToState(this.state);
    this.applyState(this.state);
  };

  TableColumnChooser.prototype.onDocumentClick = function (event) {
    if (!this.panel.contains(event.target) && !this.toggleButton.contains(event.target)) {
      this.close();
    }
  };

  TableColumnChooser.prototype.onKeydown = function (event) {
    if (event.key === 'Escape') {
      event.preventDefault();
      this.close();
    }
  };

  TableColumnChooser.prototype.bindEvents = function () {
    this.boundDocumentClick = this.onDocumentClick.bind(this);
    this.boundKeydown = this.onKeydown.bind(this);
    this.toggleButton.addEventListener(
      'click',
      function () {
        this.toggle();
      }.bind(this)
    );
  };

  function initAll() {
    document.querySelectorAll('[data-column-chooser]').forEach(function (container) {
      if (container.dataset.columnChooserInitialized === 'true') {
        return;
      }
      new TableColumnChooser(container);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }

  window.CBS = window.CBS || {};
  window.CBS.ColumnChooser = {
    init: initAll,
    TableColumnChooser: TableColumnChooser,
  };
})();
