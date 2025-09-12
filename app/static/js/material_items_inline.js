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
    return Array.from(table.querySelectorAll('input.material-id'))
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
  function getDefaultQty(){
    var setsInput = document.querySelector('input[name="material_sets"]');
    var sets = parseInt(setsInput ? setsInput.value : '0', 10);
    if(sets > 0) return sets;
    return capacity > 0 ? capacity : 0;
  }
  function initRow(row){
    var label = row.querySelector('.material-label');
    var hidden = row.querySelector('.material-id');
    var list = row.querySelector('.materials-list');
    var qty = row.querySelector('.qty-input');
    var fmtSel = row.querySelector('.fmt-select');
    var removeBtn = row.querySelector('.remove-row');
    var delFlag = row.querySelector('.delete-flag');
    if(label){
      function populate(){
        fetchOptions().then(function(data){
          list.innerHTML = '';
          (data.items||[]).forEach(function(it){
            optionData[it.id] = {langs: it.langs || [], formats: it.formats || []};
            var opt = document.createElement('option');
            opt.value = it.label;
            opt.dataset.id = it.id;
            list.appendChild(opt);
          });
        });
      }
      populate();
      label.addEventListener('input', function(){
        var match = Array.from(list.options).find(function(o){ return o.value === label.value; });
        hidden.value = match ? match.dataset.id : '';
        var meta = hidden.value ? optionData[hidden.value] : null;
        applyRestrictions(row, meta);
        if(hidden.value && !row.dataset.completed){
          row.dataset.completed = '1';
          removeBtn.style.display = '';
          if(fmtSel){
            var def = defaultFormats[hidden.value] || '';
            if(def && meta && meta.formats.indexOf(def) !== -1){
              fmtSel.value = def;
            } else {
              fmtSel.value = meta && meta.formats.length ? meta.formats[0] : '';
            }
          }
          if(!qty.value) qty.value = getDefaultQty();
          qty.focus();
          appendBlankRow();
        }
      });
      label.addEventListener('keydown', function(e){
        if(e.key === 'Escape'){
          label.value = '';
          hidden.value = '';
          applyRestrictions(row, null);
        }
      });
      label.addEventListener('focus', function(){ label.select(); });
      var clr = row.querySelector('.clear-material');
      if(clr){
        clr.addEventListener('click', function(){
          label.value = '';
          hidden.value = '';
          applyRestrictions(row, null);
        });
      }
    }
    removeBtn.addEventListener('click', function(){
      delFlag.value = '1';
      row.style.display = 'none';
    });
  }
  function applyRestrictions(row, data){
    var langSel = row.querySelector('.lang-select');
    var fmtSel = row.querySelector('.fmt-select');
    if(langSel){
      Array.from(langSel.options).forEach(function(o){
        o.hidden = data ? data.langs.indexOf(o.value) === -1 : false;
      });
      if(data && data.langs.indexOf(langSel.value) === -1){ langSel.value = ''; }
    }
    if(fmtSel){
      Array.from(fmtSel.options).forEach(function(o){
        o.hidden = data ? data.formats.indexOf(o.value) === -1 : false;
      });
      if(data && data.formats.indexOf(fmtSel.value) === -1){
        fmtSel.value = data.formats.length ? data.formats[0] : '';
      }
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
