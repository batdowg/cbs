document.addEventListener('DOMContentLoaded', function(){
  var table = document.getElementById('material-items-table');
  if(!table) return;
  var delivery = table.dataset.delivery || '';
  var lang = table.dataset.lang || '';
  var capacity = parseInt(table.dataset.capacity || '0', 10);
  var pickerUrl = '/workshop-types/material-options';
  var newIndex = 1;
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
    var removeBtn = row.querySelector('.remove-row');
    var delFlag = row.querySelector('.delete-flag');
    if(label){
      function populate(){
        fetchOptions().then(function(data){
          list.innerHTML = '';
          (data.items||[]).forEach(function(it){
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
        if(hidden.value && !row.dataset.completed){
          row.dataset.completed = '1';
          removeBtn.style.display = '';
          if(!qty.value) qty.value = getDefaultQty();
          qty.focus();
          appendBlankRow();
        }
      });
    }
    removeBtn.addEventListener('click', function(){
      delFlag.value = '1';
      row.style.display = 'none';
    });
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
