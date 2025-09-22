(function () {
  const NOTICE_DURATION = 3000;
  const NOTICE_FADE_BUFFER = 400;

  function showNotice(container, message, variant) {
    if (!container) {
      return;
    }
    const host = container.querySelector('[data-attendance-notices]');
    if (!host) {
      return;
    }

    if (typeof host._cancelNotice === 'function') {
      host._cancelNotice();
    }
    while (host.firstChild) {
      host.removeChild(host.firstChild);
    }

    const notice = document.createElement('div');
    notice.className = 'attendance-notice';
    if (variant === 'error') {
      notice.classList.add('attendance-notice-error');
    }
    notice.setAttribute('role', 'status');
    notice.appendChild(document.createTextNode(message));
    host.appendChild(notice);

    const fadeTimeout = window.setTimeout(function () {
      notice.classList.add('is-fading');
    }, NOTICE_DURATION);

    const removeTimeout = window.setTimeout(function () {
      if (notice.parentElement === host) {
        host.removeChild(notice);
      }
      if (host._cancelNotice === cancel) {
        host._cancelNotice = null;
      }
    }, NOTICE_DURATION + NOTICE_FADE_BUFFER);

    function cancel() {
      window.clearTimeout(fadeTimeout);
      window.clearTimeout(removeTimeout);
      if (notice.parentElement === host) {
        host.removeChild(notice);
      }
      host._cancelNotice = null;
    }

    host._cancelNotice = cancel;

    notice.addEventListener('transitionend', function (event) {
      if (event.propertyName === 'opacity' && notice.classList.contains('is-fading')) {
        if (notice.parentElement === host) {
          host.removeChild(notice);
        }
        if (host._cancelNotice === cancel) {
          host._cancelNotice = null;
        }
      }
    });
  }

  function sendJson(url, payload) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'same-origin',
      body: JSON.stringify(payload || {}),
    }).then(function (response) {
      return response
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          if (!response.ok || (data && data.ok === false)) {
            const message = (data && data.error) || response.statusText || 'Request failed.';
            const error = new Error(message);
            error.data = data;
            throw error;
          }
          return data || {};
        });
    });
  }

  function handleToggle(event) {
    event.preventDefault();
    const checkbox = event.target;
    const container = checkbox.closest('[data-attendance-table]');
    if (!container) {
      return;
    }
    const toggleUrl = container.dataset.toggleUrl;
    if (!toggleUrl) {
      return;
    }
    const participantId = checkbox.getAttribute('data-participant-id');
    const dayIndex = checkbox.getAttribute('data-day-index');
    const newState = checkbox.checked;
    const previousState = !newState;
    checkbox.disabled = true;
    sendJson(toggleUrl, {
      participant_id: participantId,
      day_index: dayIndex,
      attended: newState,
    })
      .then(function (data) {
        checkbox.checked = Boolean(data.attended);
        checkbox.dataset.lastValue = checkbox.checked ? 'true' : 'false';
        showNotice(container, 'Saved');
      })
      .catch(function (error) {
        checkbox.checked = previousState;
        showNotice(container, error.message || 'Unable to update attendance.', 'error');
      })
      .finally(function () {
        checkbox.disabled = false;
      });
  }

  function handleMarkAll(event) {
    const button = event.target;
    const container = button.closest('[data-attendance-table]');
    if (!container) {
      return;
    }
    const markAllUrl = container.dataset.markAllUrl;
    if (!markAllUrl) {
      return;
    }
    button.disabled = true;
    sendJson(markAllUrl, {})
      .then(function (data) {
        container.querySelectorAll('[data-attendance-checkbox]').forEach(function (checkbox) {
          checkbox.checked = true;
          checkbox.dataset.lastValue = 'true';
        });
        showNotice(container, 'All marked attended');
      })
      .catch(function (error) {
        showNotice(container, error.message || 'Unable to mark attendance.', 'error');
      })
      .finally(function () {
        button.disabled = false;
      });
  }

  function initTable(container) {
    const toggleUrl = container.dataset.toggleUrl;
    const markAllUrl = container.dataset.markAllUrl;
    if (!toggleUrl && !markAllUrl) {
      return;
    }
    container.querySelectorAll('[data-attendance-checkbox]').forEach(function (checkbox) {
      checkbox.addEventListener('change', handleToggle);
      checkbox.dataset.lastValue = checkbox.checked ? 'true' : 'false';
    });
    const markAllButton = container.querySelector('[data-mark-all-attended]');
    if (markAllButton) {
      markAllButton.addEventListener('click', function (event) {
        event.preventDefault();
        handleMarkAll(event);
      });
    }
  }

  function initAttendance(context) {
    context
      .querySelectorAll('[data-attendance-table]')
      .forEach(function (container) {
        initTable(container);
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initAttendance(document);
  });

  window.initAttendanceControls = function () {
    initAttendance(document);
  };
})();
