document.addEventListener('DOMContentLoaded', function () {
  var table = document.getElementById('defaults-table');
  if (!table) return;
  var newIndex = 1;

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

  function isComplete(row) {
    var delivery = document.querySelector('[name="defaults[' + row + '][delivery_type]"]');
    var region = document.querySelector('[name="defaults[' + row + '][region_code]"]');
    var lang = document.querySelector('[name="defaults[' + row + '][language]"]');
    var hidden = document.querySelector('input.material-id[data-row="' + row + '"]');
    return (
      delivery && region && lang && hidden &&
      delivery.value && region.value && lang.value && hidden.value
    );
  }

  function checkLastRow() {
    var blankRow = table.querySelector('tr[data-blank-row="true"]');
    if (!blankRow) return;
    var row = blankRow.dataset.row;
    if (isComplete(row)) {
      blankRow.removeAttribute('data-blank-row');
      appendBlankRow(row);
    }
  }

  function appendBlankRow(copyFrom) {
    var tpl = document.getElementById('default-row-template');
    if (!tpl) return;
    var rowId = 'new' + newIndex++;
    var html = tpl.innerHTML.replace(/__index__/g, rowId);
    var temp = document.createElement('tbody');
    temp.innerHTML = html.trim();
    var newRow = temp.firstElementChild;
    table.appendChild(newRow);
    ['delivery_type', 'region_code', 'language', 'default_format'].forEach(function (field) {
      var prev = document.querySelector('[name="defaults[' + copyFrom + '][' + field + ']"]');
      var curr = document.querySelector('[name="defaults[' + rowId + '][' + field + ']"]');
      if (prev && curr) curr.value = prev.value;
    });
    var prevActive = document.querySelector('[name="defaults[' + copyFrom + '][active]"]');
    var currActive = document.querySelector('[name="defaults[' + rowId + '][active]"]');
    if (prevActive && currActive) currActive.checked = prevActive.checked;
    initRow(rowId);
  }

  function bindMaterialInput(row, inp) {
    inp.addEventListener('input', function () {
      var list = document.getElementById('materials-' + row);
      var match = Array.prototype.find.call(list.options, function (o) {
        return o.value === inp.value;
      });
      var hidden = document.querySelector('input.material-id[data-row="' + row + '"]');
      hidden.value = match ? match.dataset.id : '';
      checkLastRow();
    });
  }

  function initRow(row) {
    populate(row);
    var inp = document.querySelector('input.material-label[data-row="' + row + '"]');
    if (inp) bindMaterialInput(row, inp);
    var langSel = document.querySelector('.lang-select[data-row="' + row + '"]');
    if (langSel) {
      langSel.addEventListener('change', function () {
        populate(row);
        checkLastRow();
      });
    }
    var delSel = document.querySelector('.delivery-select[data-row="' + row + '"]');
    if (delSel) {
      delSel.addEventListener('change', function () {
        populate(row);
        checkLastRow();
      });
    }
    var showAll = document.querySelector('.show-all[data-row="' + row + '"]');
    if (showAll) {
      showAll.addEventListener('change', function () {
        populate(row);
        checkLastRow();
      });
    }
    var regionSel = document.querySelector('[name="defaults[' + row + '][region_code]"]');
    if (regionSel) {
      regionSel.addEventListener('change', checkLastRow);
    }
  }

  table.querySelectorAll('tr[data-row]').forEach(function (tr) {
    initRow(tr.dataset.row);
  });
});

