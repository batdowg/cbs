document.addEventListener('DOMContentLoaded', function () {
  var table = document.getElementById('defaults-table');
  if (!table) return;
  var newIndex = 1;
  var optionData = {};

  function fetchOptions(row) {
    var langSel = document.querySelector('[name="defaults[' + row + '][language]"]');
    var delSel = document.querySelector('[name="defaults[' + row + '][delivery_type]"]');
    var lang = langSel ? langSel.value : '';
    var delivery = delSel ? delSel.value : '';
    var params = new URLSearchParams();
    if (delivery) params.append('delivery_type', delivery);
    if (lang) params.append('lang', lang);
    return fetch('/workshop-types/material-options?' + params.toString())
      .then(function (r) { return r.json(); });
  }

  function populate(row) {
    fetchOptions(row).then(function (data) {
      var sel = document.querySelector('select.material-select[data-row="' + row + '"]');
      if (!sel) return;
      var current = sel.value;
      sel.innerHTML = '';
      var blank = document.createElement('option');
      blank.value = '';
      sel.appendChild(blank);
      var found = false;
      (data.items || []).forEach(function (it) {
        optionData[it.id] = { langs: it.langs || [], formats: it.formats || [] };
        var opt = document.createElement('option');
        opt.value = it.id;
        opt.textContent = it.label;
        sel.appendChild(opt);
        if (String(it.id) === current) found = true;
      });
      if (found) {
        sel.value = current;
        applyRestrictions(row, optionData[current]);
      } else {
        sel.value = '';
        applyRestrictions(row, null);
      }
    });
  }

  function applyRestrictions(row, data) {
    var langSel = document.querySelector('[name="defaults[' + row + '][language]"]');
    var fmtSel = document.querySelector('[name="defaults[' + row + '][default_format]"]');
    if (langSel) {
      Array.prototype.forEach.call(langSel.options, function (opt) {
        opt.hidden = data ? data.langs.indexOf(opt.value) === -1 : false;
      });
      if (data && data.langs.indexOf(langSel.value) === -1) {
        langSel.value = '';
      }
    }
    if (fmtSel) {
      Array.prototype.forEach.call(fmtSel.options, function (opt) {
        opt.hidden = data ? data.formats.indexOf(opt.value) === -1 : false;
      });
      if (data && data.formats.indexOf(fmtSel.value) === -1) {
        fmtSel.value = data.formats[0] || '';
      }
    }
  }

  function isComplete(row) {
    var delivery = document.querySelector('[name="defaults[' + row + '][delivery_type]"]');
    var region = document.querySelector('[name="defaults[' + row + '][region_code]"]');
    var lang = document.querySelector('[name="defaults[' + row + '][language]"]');
    var sel = document.querySelector('select.material-select[data-row="' + row + '"]');
    return (
      delivery && region && lang && sel &&
      delivery.value && region.value && lang.value && sel.value
    );
  }

  function checkLastRow() {
    var blankRow = table.querySelector('tbody tr[data-blank-row="true"]');
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
    var body = table.tBodies[0] || table;
    body.appendChild(newRow);
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

  function initRow(row) {
    populate(row);
    var sel = document.querySelector('select.material-select[data-row="' + row + '"]');
    if (sel) {
      sel.addEventListener('change', function () {
        var meta = sel.value ? optionData[sel.value] : null;
        applyRestrictions(row, meta);
        checkLastRow();
      });
    }
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
    var regionSel = document.querySelector('[name="defaults[' + row + '][region_code]"]');
    if (regionSel) {
      regionSel.addEventListener('change', checkLastRow);
    }
  }

  table.querySelectorAll('tbody tr[data-row]').forEach(function (tr) {
    initRow(tr.dataset.row);
  });
});
