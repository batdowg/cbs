document.addEventListener('DOMContentLoaded', function () {
  function fetchOptions(row) {
    var langSel = document.querySelector('[name="defaults[' + row + '][language]"]');
    var delSel = document.querySelector('[name="defaults[' + row + '][delivery_type]"]');
    var lang = langSel ? langSel.value : '';
    var delivery = delSel ? delSel.value : '';
    var showAll = document.querySelector('.show-all[data-row="' + row + '"]');
    var params = new URLSearchParams();
    if (delivery) params.append('delivery_type', delivery);
    if (lang) params.append('lang', lang);
    if (showAll && showAll.checked) params.append('include_bulk', '1');
    return fetch('/workshop-types/material-options?' + params.toString())
      .then(function (r) { return r.json(); });
  }

  function populate(row) {
    fetchOptions(row).then(function (data) {
      var list = document.getElementById('materials-' + row);
      if (!list) return;
      list.innerHTML = '';
      (data.items || []).forEach(function (it) {
        var opt = document.createElement('option');
        opt.value = it.label;
        opt.dataset.id = it.id;
        list.appendChild(opt);
      });
      var hidden = document.querySelector('input.material-id[data-row="' + row + '"]');
      var input = document.querySelector('input.material-label[data-row="' + row + '"]');
      if (hidden && input && hidden.value) {
        var match = (data.items || []).find(function (it) {
          return String(it.id) === hidden.value;
        });
        if (match) input.value = match.label;
      }
    });
  }

  document.querySelectorAll('input.material-label').forEach(function (inp) {
    var row = inp.dataset.row;
    populate(row);
    inp.addEventListener('input', function () {
      var list = document.getElementById('materials-' + row);
      var match = Array.prototype.find.call(list.options, function (o) {
        return o.value === inp.value;
      });
      var hidden = document.querySelector('input.material-id[data-row="' + row + '"]');
      if (match) hidden.value = match.dataset.id;
      else hidden.value = '';
    });
  });

  ['.lang-select', '.show-all', '.delivery-select'].forEach(function (sel) {
    document.querySelectorAll(sel).forEach(function (el) {
      el.addEventListener('change', function () { populate(el.dataset.row); });
    });
  });
});

