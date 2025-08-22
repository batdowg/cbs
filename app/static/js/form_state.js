document.addEventListener('DOMContentLoaded', function () {
  var form = document.querySelector('form');
  if (!form) return;
  var key = 'formState:' + window.location.pathname;
  // restore
  try {
    var saved = JSON.parse(localStorage.getItem(key) || '{}');
    for (var name in saved) {
      var el = form.elements[name];
      if (!el) continue;
      if (el.type === 'checkbox' || el.type === 'radio') {
        el.checked = saved[name];
      } else {
        el.value = saved[name];
      }
    }
  } catch (e) {}
  function save() {
    var data = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name) return;
      if (el.type === 'checkbox' || el.type === 'radio') {
        data[el.name] = el.checked;
      } else {
        data[el.name] = el.value;
      }
    });
    try {
      localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {}
  }
  form.addEventListener('change', save);
  form.addEventListener('input', save);
});
