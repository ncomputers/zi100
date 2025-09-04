// Handles global page fade transitions
window.addEventListener('DOMContentLoaded', () => {
  const fade=document.getElementById('page-fade');
  if(!fade) return;
  fade.classList.add('hidden');
  window.addEventListener('beforeunload', () => {
    fade.classList.remove('hidden');
  });
});
