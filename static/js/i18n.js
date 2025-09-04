async function applyTranslations(page) {
  const lang = document.documentElement.lang || 'en';
  try {
    const resp = await fetch(`/static/locales/${lang}/${page}.json`);
    if (!resp.ok) return;
    const dict = await resp.json();
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (dict[key]) el.textContent = dict[key];
    });
    document.querySelectorAll('[data-i18n-label]').forEach(el => {
      const key = el.getAttribute('data-i18n-label');
      if (dict[key]) el.setAttribute('aria-label', dict[key]);
    });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (dict[key]) el.setAttribute('placeholder', dict[key]);
    });
  } catch (err) {
    console.error('i18n load failed', err);
  }
}
window.applyTranslations = applyTranslations;
