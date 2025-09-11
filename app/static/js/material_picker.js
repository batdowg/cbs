document.addEventListener('DOMContentLoaded', function () {
  var dataEl = document.getElementById('material-data');
  if (!dataEl) return;
  var items = JSON.parse(dataEl.textContent || '[]');
  var itemMap = {};
  items.forEach(function (it) {
    itemMap['materials_options:' + it.id] = it;
  });
  function populate(row) {
    var langSel = document.querySelector('[name="language_' + row + '"]');
    if (!langSel) return;
    var lang = langSel.value;
    var showAll = document.querySelector('.show-all[data-row="' + row + '"]');
    showAll = showAll && showAll.checked;
    var list = document.getElementById('materials-' + row);
    list.innerHTML = '';
    items.forEach(function (it) {
      if (!showAll && lang && it.languages.length && it.languages.indexOf(lang) === -1) {
        return;
      }
      var opt = document.createElement('option');
      opt.value = it.label;
      opt.dataset.ref = 'materials_options:' + it.id;
      list.appendChild(opt);
    });
    var input = document.querySelector('input.material-item[data-row="' + row + '"]');
    var sel = input.dataset.selected || input.dataset.ref;
    if (sel && itemMap[sel]) {
      input.value = itemMap[sel].label;
      input.dataset.ref = sel;
    } else {
      input.value = '';
      input.dataset.ref = '';
    }
    input.dataset.selected = '';
  }
  document.querySelectorAll('input.material-item').forEach(function (inp) {
    var row = inp.dataset.row;
    populate(row);
    inp.addEventListener('input', function () {
      var list = document.getElementById('materials-' + row);
      var match = Array.prototype.find.call(list.options, function (o) {
        return o.value === inp.value;
      });
      if (match) {
        inp.dataset.ref = match.dataset.ref;
      } else {
        inp.dataset.ref = '';
      }
    });
  });
  document.querySelectorAll('.lang-select').forEach(function (sel) {
    sel.addEventListener('change', function () {
      populate(sel.dataset.row);
    });
  });
  document.querySelectorAll('.show-all').forEach(function (chk) {
    chk.addEventListener('change', function () {
      populate(chk.dataset.row);
    });
  });
  var form = document.querySelector('form');
  if (form) {
    form.addEventListener('submit', function () {
      document.querySelectorAll('input.material-item').forEach(function (inp) {
        if (inp.dataset.ref) {
          inp.value = inp.dataset.ref;
        }
      });
    });
  }
});
