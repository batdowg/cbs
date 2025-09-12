document.addEventListener('DOMContentLoaded', function(){
  var table = document.getElementById('material-items-table');
  if(!table) return;
  var delivery = table.dataset.delivery || '';
  var lang = table.dataset.lang || '';
  var capacity = parseInt(table.dataset.capacity || '0', 10);
  var defaultFormats = {};
  try { defaultFormats = JSON.parse(table.dataset.defaultFormats || '{}'); } catch(e) {}
  var pickerUrl = '/workshop-types/material-options';
  var newIndex = 1;
  var optionData = {};

  function selectedIds(){
    return Array.from(table.querySelectorAll('[name$="[option_id]"]'))
      .map(function(i){ return i.value; }).filter(Boolean);
  }

  function fetchOptions(){
    var params = new URLSearchParams();
    if(delivery) params.append('delivery_type', delivery);
    if(lang) params.append('lang', lang);
    var exclude = selectedIds();
    if(exclude.length) params.append('exclude', exclude.join(','));
    return fetch(pickerUrl + '?' + params.toString()).then(function(r){ return r.json(); });
  }

  function getDefaultQty(meta){
    if(meta && meta.basis === 'Per order') return 1;
    var setsInput = document.querySelector('input[name="material_sets"]');
    var sets = parseInt(setsInput ? setsInput.value : '0', 10);
    if(sets > 0) return sets;
    return capacity > 0 ? capacity : 0;
  }

  function applyRestrictions(row, meta){
    var langSel = row.querySelector('.lang-select');
    var fmtSel = row.querySelector('.fmt-select');
    if(langSel){
      Array.from(langSel.options).forEach(function(o){
        o.hidden = meta ? meta.langs.indexOf(o.value) === -1 : false;
      });
      if(meta && meta.langs.indexOf(langSel.value) === -1){ langSel.value = ''; }
    }
    if(fmtSel){
      Array.from(fmtSel.options).forEach(function(o){
        o.hidden = meta ? meta.formats.indexOf(o.value) === -1 : false;
      });
      if(meta && meta.formats.indexOf(fmtSel.value) === -1){
        fmtSel.value = meta.formats.length ? meta.formats[0] : '';
      }
    }
  }

  function initRow(row){
    var sel = row.querySelector('.material-select');
    var qty = row.querySelector('.qty-input');
    var fmtSel = row.querySelector('.fmt-select');
    var removeBtn = row.querySelector('.remove-row');
    var delFlag = row.querySelector('.delete-flag');

    function populate(){
      fetchOptions().then(function(data){
        if(!sel) return;
        var current = sel.value;
        sel.innerHTML = '<option value=""></option>';
        var found = false;
        (data.items||[]).forEach(function(it){
          optionData[it.id] = {langs: it.langs||[], formats: it.formats||[], basis: it.basis};
          var opt = document.createElement('option');
          opt.value = it.id;
          opt.textContent = it.label;
          sel.appendChild(opt);
          if(String(it.id) === current) found = true;
        });
        if(found){
          sel.value = current;
          applyRestrictions(row, optionData[current]);
        } else {
          sel.value = '';
          applyRestrictions(row, null);
        }
      });
    }

    if(sel){
      populate();
      sel.addEventListener('change', function(){
        var meta = sel.value ? optionData[sel.value] : null;
        applyRestrictions(row, meta);
        if(sel.value && !row.dataset.completed){
          row.dataset.completed = '1';
          if(removeBtn) removeBtn.style.display = '';
          if(fmtSel){
            var def = defaultFormats[sel.value] || '';
            if(def && meta && meta.formats.indexOf(def) !== -1){
              fmtSel.value = def;
            } else {
              fmtSel.value = meta && meta.formats.length ? meta.formats[0] : '';
            }
          }
          if(qty && !qty.value) qty.value = getDefaultQty(meta);
          if(qty) qty.focus();
          appendBlankRow();
        }
      });
    }

    if(removeBtn){
      removeBtn.addEventListener('click', function(){
        if(delFlag) delFlag.value = '1';
        row.style.display = 'none';
      });
    }
  }

  function appendBlankRow(){
    var tpl = document.getElementById('item-row-template');
    if(!tpl) return;
    var html = tpl.innerHTML.replace(/__index__/g, 'new' + newIndex++);
    var temp = document.createElement('tbody');
    temp.innerHTML = html.trim();
    var row = temp.firstElementChild;
    table.appendChild(row);
    initRow(row);
  }

  table.querySelectorAll('tr[data-existing]').forEach(initRow);
  appendBlankRow();
});
