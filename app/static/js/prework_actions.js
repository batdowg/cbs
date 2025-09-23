(function () {
  'use strict';

  var container = document.querySelector('[data-prework-table]');
  if (!container) {
    return;
  }

  var feedbackRoot = document.querySelector('[data-prework-feedback]');
  var CATEGORY_MAP = {
    success: 'success',
    error: 'error',
    warning: 'warning',
    info: 'info',
    danger: 'error'
  };

  function showFeedback(message, category) {
    if (!feedbackRoot || !message) {
      return;
    }
    var normalized = CATEGORY_MAP[category] || 'info';
    feedbackRoot.innerHTML = '';
    var alert = document.createElement('div');
    alert.className = 'flash flash-' + normalized;
    alert.setAttribute('role', 'status');
    alert.textContent = message;
    feedbackRoot.appendChild(alert);
  }

  function updateStatuses(statuses) {
    if (!statuses || typeof statuses !== 'object') {
      return;
    }
    Object.keys(statuses).forEach(function (participantId) {
      var cell = container.querySelector(
        '[data-prework-status-cell][data-participant-id="' + participantId + '"]'
      );
      if (!cell) {
        return;
      }
      var statusData = statuses[participantId] || {};
      var labelEl = cell.querySelector('[data-prework-status-label]');
      if (labelEl) {
        labelEl.textContent = statusData.label || 'Not sent';
      }
      if (statusData.is_waived) {
        var actionForm = cell.querySelector('form[data-prework-send]');
        if (actionForm) {
          actionForm.remove();
        }
      }
    });
  }

  function collectParticipantIds(form) {
    var formData = new FormData(form);
    var ids = formData.getAll('participant_ids[]');
    if (!ids.length) {
      ids = formData.getAll('participant_ids');
    }
    var cleaned = [];
    ids.forEach(function (value) {
      if (value !== null && value !== undefined && String(value).trim() !== '') {
        cleaned.push(String(value));
      }
    });
    return cleaned;
  }

  function handleSubmit(event) {
    event.preventDefault();
    var form = event.currentTarget;
    if (!form || form.dataset.preworkSubmitting === '1') {
      return;
    }
    form.dataset.preworkSubmitting = '1';
    var submitButton = form.querySelector('[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
    }
    var payload = {};
    var participantIds = collectParticipantIds(form);
    if (participantIds.length) {
      payload.participant_ids = participantIds;
    }

    var requestInit = {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify(payload)
    };

    fetch(form.action, requestInit)
      .then(function (response) {
        var contentType = response.headers.get('content-type') || '';
        var expectsJson = contentType.indexOf('application/json') !== -1;
        if (!expectsJson) {
          throw new Error('non-json-response');
        }
        return response
          .json()
          .then(function (data) {
            return { response: response, data: data };
          })
          .catch(function () {
            throw new Error('invalid-json');
          });
      })
      .then(function (result) {
        var response = result.response;
        var data = result.data || {};
        if (!response.ok && response.status !== 207) {
          if (data.error) {
            showFeedback(data.error, 'error');
            return;
          }
          throw new Error('request-failed');
        }
        updateStatuses(data.statuses);
        if (data.message) {
          showFeedback(data.message, data.message_category || 'info');
        }
      })
      .catch(function () {
        delete form.dataset.preworkSubmitting;
        if (submitButton) {
          submitButton.disabled = false;
        }
        form.submit();
      })
      .finally(function () {
        delete form.dataset.preworkSubmitting;
        if (submitButton) {
          submitButton.disabled = false;
        }
      });
  }

  container.querySelectorAll('form[data-prework-send]').forEach(function (form) {
    form.addEventListener('submit', handleSubmit);
  });
})();
