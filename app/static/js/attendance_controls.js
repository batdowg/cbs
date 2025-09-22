(function () {
  function showFlash(message, category) {
    const content = document.querySelector('.content');
    if (!content) {
      return;
    }
    let container = content.querySelector('.flashes');
    if (!container) {
      container = document.createElement('div');
      container.className = 'flashes';
      content.insertBefore(container, content.firstChild);
    }
    const flash = document.createElement('div');
    const variant = category || 'info';
    flash.className = 'flash flash-' + variant;
    flash.setAttribute('role', 'alert');
    flash.setAttribute('aria-live', 'polite');
    flash.tabIndex = 0;
    flash.appendChild(document.createTextNode(message));
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'flash-close btn-icon';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.textContent = '×';
    closeBtn.addEventListener('click', function () {
      flash.remove();
    });
    flash.appendChild(closeBtn);
    container.appendChild(flash);
    flash.focus();
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
    const participantName = checkbox.getAttribute('data-participant-name') || 'participant';
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
        showFlash('Updated Day ' + dayIndex + ' attendance for ' + participantName + '.', 'success');
      })
      .catch(function (error) {
        checkbox.checked = previousState;
        showFlash(error.message || 'Unable to update attendance.', 'error');
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
        const updated = data.updated_count != null ? Number(data.updated_count) : null;
        if (updated && !Number.isNaN(updated)) {
          showFlash('Marked attendance for ' + updated + ' entries.', 'success');
        } else {
          showFlash('Marked attendance for all participants.', 'success');
        }
      })
      .catch(function (error) {
        showFlash(error.message || 'Unable to mark attendance.', 'error');
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
