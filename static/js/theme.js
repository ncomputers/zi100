// Purpose: shared theme management
(function(){
  const body = document.body;
  const listeners = [];

  function applyTheme(){
    if(localStorage.getItem('dark-mode') === 'true'){
      body.classList.add('dark-mode');
    } else {
      body.classList.remove('dark-mode');
    }
    listeners.forEach(fn => { try{ fn(); } catch(e){} });

  }

  function toggleTheme(){
    const dark = body.classList.toggle('dark-mode');
    localStorage.setItem('dark-mode', dark);
    applyTheme();
  }

  function onChange(fn){
    if(typeof fn === 'function') listeners.push(fn);
  }

  document.querySelectorAll('.dark-toggle').forEach(btn => {
    btn.addEventListener('click', toggleTheme);
  });
  applyTheme();
  window.theme = { applyTheme, toggleTheme, onChange };

})();
