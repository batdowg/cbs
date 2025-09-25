(function () {
  function enhance(select) {
    if (select.dataset.searchableApplied === '1') {
      return;
    }
    select.dataset.searchableApplied = '1';
    var wrapper = document.createElement('div');
    wrapper.className = 'searchable-select';
    var search = document.createElement('input');
    search.type = 'search';
    search.className = 'searchable-select__input';
    search.placeholder = select.getAttribute('data-search-placeholder') || 'Search…';
    var parent = select.parentNode;
    parent.insertBefore(wrapper, select);
    wrapper.appendChild(search);
    wrapper.appendChild(select);
    var options = Array.prototype.slice.call(select.options || []);

    function updateVisibility(term) {
      var normalized = term.trim().toLowerCase();
      var anyVisible = false;
      options.forEach(function (option) {
        if (!option.value) {
          option.style.display = normalized ? 'none' : '';
          if (!normalized) {
            anyVisible = true;
          }
          return;
        }
        var label = (option.textContent || '').toLowerCase();
        var match = !normalized || label.indexOf(normalized) !== -1;
        option.style.display = match ? '' : 'none';
        if (match) {
          anyVisible = true;
        }
      });
      wrapper.classList.toggle('searchable-select--no-results', !anyVisible);
    }

    search.addEventListener('input', function () {
      updateVisibility(search.value);
    });

    select.addEventListener('change', function () {
      var selected = select.options[select.selectedIndex];
      if (selected && selected.style.display === 'none') {
        search.value = '';
        updateVisibility('');
      }
    });
  }

  function init() {
    var selects = document.querySelectorAll('select[data-searchable-select]');
    selects.forEach(enhance);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
