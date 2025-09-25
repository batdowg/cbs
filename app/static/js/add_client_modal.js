(function (window, document) {
  'use strict';

  function toArray(value) {
    if (!value) {
      return [];
    }
    if (Array.isArray(value)) {
      return value.slice();
    }
    if (typeof value.length === 'number') {
      return Array.prototype.slice.call(value);
    }
    return [value];
  }

  function createOption(doc, value, label) {
    if (doc && typeof doc.createElement === 'function') {
      var option = doc.createElement('option');
      option.value = String(value);
      option.textContent = label;
      return option;
    }
    return { value: String(value), textContent: label, selected: false };
  }

  function appendOption(select, option) {
    if (!select) {
      return;
    }
    if (typeof select.appendChild === 'function') {
      select.appendChild(option);
      return;
    }
    if (Array.isArray(select.options) && typeof select.options.push === 'function') {
      select.options.push(option);
      return;
    }
    if (!select.options) {
      select.options = [];
    }
    select.options = select.options.concat(option);
  }

  function findOption(select, value) {
    var options = toArray(select && select.options);
    for (var i = 0; i < options.length; i += 1) {
      if (String(options[i].value) === String(value)) {
        return options[i];
      }
    }
    return null;
  }

  function clearFieldError(form, name) {
    if (!form) {
      return;
    }
    var field = form.querySelector('[name="' + name + '"]');
    if (field && field.classList && field.classList.remove) {
      field.classList.remove('error');
    }
  }

  function setFieldError(form, name) {
    if (!form) {
      return;
    }
    var field = form.querySelector('[name="' + name + '"]');
    if (field && field.classList && field.classList.add) {
      field.classList.add('error');
    }
  }

  function createController(root) {
    var doc = root || document;
    var dialog = doc.querySelector('[data-add-client-modal]');
    if (!dialog) {
      return null;
    }
    var form = dialog.querySelector('form[data-add-client-form]') || dialog.querySelector('form');
    if (!form) {
      return null;
    }
    var cancelBtn = dialog.querySelector('[data-add-client-cancel]');
    var nameInput = form.querySelector('input[name="name"]');
    var regionSelect = form.querySelector('select[name="data_region"]');
    var activeInput = form.querySelector('input[name="is_active"]');
    var errorBlocks = toArray(form.querySelectorAll('[data-error-for]'));
    var activeSelect = null;

    function clearErrors() {
      errorBlocks.forEach(function (block) {
        if (!block) {
          return;
        }
        block.textContent = '';
        if (typeof block.hidden !== 'undefined') {
          block.hidden = true;
        }
      });
      clearFieldError(form, 'name');
      clearFieldError(form, 'data_region');
    }

    function showErrors(errors) {
      if (!errors) {
        return;
      }
      var keys = Object.keys(errors);
      keys.forEach(function (key) {
        var message = errors[key];
        if (key === 'name' || key === 'data_region') {
          setFieldError(form, key);
        }
        errorBlocks.forEach(function (block) {
          if (!block) {
            return;
          }
          var fieldName = block.getAttribute ? block.getAttribute('data-error-for') : null;
          if (fieldName === key) {
            block.textContent = message;
            if (typeof block.hidden !== 'undefined') {
              block.hidden = false;
            }
          }
        });
      });
    }

    function openFor(select) {
      activeSelect = select;
      if (typeof form.reset === 'function') {
        form.reset();
      }
      clearErrors();
      if (activeInput) {
        activeInput.checked = true;
      }
      if (dialog && typeof dialog.showModal === 'function') {
        dialog.showModal();
      }
      if (nameInput && typeof nameInput.focus === 'function') {
        nameInput.focus();
      }
    }

    function closeDialog() {
      if (dialog && typeof dialog.close === 'function') {
        dialog.close();
      }
    }

    function ensureOptionForAll(client) {
      if (!client || client.id === undefined) {
        return;
      }
      var selects = toArray(doc.querySelectorAll('select[data-client-select]'));
      selects.forEach(function (select) {
        if (!select) {
          return;
        }
        var option = findOption(select, client.id);
        if (!option) {
          option = createOption(doc, client.id, client.name || '');
          appendOption(select, option);
        } else if (option && client.name) {
          option.textContent = client.name;
        }
      });
    }

    function submitForm(event) {
      if (event && typeof event.preventDefault === 'function') {
        event.preventDefault();
      }
      if (!activeSelect) {
        showErrors({ __all__: 'Select a participant row before adding a client.' });
        return;
      }
      if (typeof window.FormData !== 'function') {
        showErrors({ __all__: 'Form submission is not supported in this browser.' });
        return;
      }
      clearErrors();
      var formData = new window.FormData(form);
      var activeValue = formData.get('is_active');
      var isActive = false;
      if (activeValue !== null && activeValue !== undefined) {
        var flag = String(activeValue).toLowerCase();
        isActive = flag === '1' || flag === 'true' || flag === 'on' || flag === 'active';
      }
      formData.set('status', isActive ? 'active' : 'inactive');
      formData.delete('is_active');
      window.fetch('/clients/inline-new', { method: 'POST', body: formData })
        .then(function (response) {
          return response
            .json()
            .catch(function () {
              return {};
            })
            .then(function (data) {
              return { status: response.status, data: data };
            });
        })
        .then(function (result) {
          if (!result) {
            showErrors({ __all__: 'Unable to save client. Try again.' });
            return;
          }
          if (result.status === 200 && result.data && result.data.id) {
            ensureOptionForAll(result.data);
            if (activeSelect) {
              activeSelect.value = String(result.data.id);
              if (typeof activeSelect.options === 'object') {
                var createdOption = findOption(activeSelect, result.data.id);
                if (createdOption) {
                  createdOption.selected = true;
                }
              }
              if (typeof activeSelect.dispatchEvent === 'function' && typeof window.Event === 'function') {
                try {
                  activeSelect.dispatchEvent(new window.Event('change', { bubbles: true }));
                } catch (err) {
                  var evt = { type: 'change', bubbles: true, target: activeSelect };
                  activeSelect.dispatchEvent(evt);
                }
              }
            }
            closeDialog();
            if (typeof form.reset === 'function') {
              form.reset();
            }
            return;
          }
          if (result.data && result.data.errors) {
            showErrors(result.data.errors);
            return;
          }
          showErrors({ __all__: 'Unable to save client. Try again.' });
        })
        .catch(function () {
          showErrors({ __all__: 'Unable to save client. Try again.' });
        });
    }

    var triggers = toArray(doc.querySelectorAll('[data-add-client-trigger]'));
    triggers.forEach(function (trigger) {
      if (!trigger || typeof trigger.addEventListener !== 'function') {
        return;
      }
      trigger.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') {
          event.preventDefault();
        }
        var selectId = null;
        if (trigger.getAttribute) {
          selectId = trigger.getAttribute('data-target-select');
        }
        var select = null;
        if (selectId) {
          if (typeof doc.getElementById === 'function') {
            select = doc.getElementById(selectId);
          }
        }
        if (!select && trigger.previousElementSibling) {
          select = trigger.previousElementSibling;
        }
        if (!select) {
          return;
        }
        openFor(select);
      });
    });

    if (cancelBtn && typeof cancelBtn.addEventListener === 'function') {
      cancelBtn.addEventListener('click', function (event) {
        if (event && typeof event.preventDefault === 'function') {
          event.preventDefault();
        }
        closeDialog();
      });
    }

    if (typeof form.addEventListener === 'function') {
      form.addEventListener('submit', submitForm);
    }

    return {
      openFor: openFor,
      close: closeDialog,
      setActiveSelect: function (select) {
        activeSelect = select;
      },
      ensureOptionForAll: ensureOptionForAll,
      clearErrors: clearErrors,
      showErrors: showErrors,
    };
  }

  function init() {
    return createController(document);
  }

  var api = {
    init: init,
    createController: createController,
  };

  window.CBSAddClientModal = api;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window, document);
