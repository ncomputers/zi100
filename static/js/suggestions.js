export function initSuggestions() {
  const nameField = document.querySelector('input[name="name"]');
  const phoneField = document.getElementById('phone');
  const emailField = document.querySelector('input[name="email"]');

  async function fetchSuggestions(prefix) {
    if (prefix.length < 2) return [];
    const resp = await fetch('/api/visitors/suggest?name_prefix=' + encodeURIComponent(prefix));
    return resp.ok ? resp.json() : [];
  }

  function updateLists(items) {
    const nlist = document.getElementById('nameSuggestions');
    const plist = document.getElementById('phoneSuggestions');
    nlist.innerHTML = '';
    plist.innerHTML = '';
    items.forEach(it => {
      const no = document.createElement('option');
      no.value = it.name;
      nlist.appendChild(no);
      const po = document.createElement('option');
      po.value = it.phone;
      plist.appendChild(po);
    });
  }

  nameField.addEventListener('input', async e => {
    updateLists(await fetchSuggestions(e.target.value));
  });

  phoneField.addEventListener('input', async e => {
    const val = e.target.value.replace(/\D/g, '');
    updateLists(await fetchSuggestions(val));
  });

  phoneField.addEventListener('change', async e => {
    const ph = e.target.value.replace(/\D/g, '');
    if (ph.length < 3) return;
    const r = await fetch('/invite/lookup?phone=' + ph);
    if (r.ok) {
      const d = await r.json();
      if (d.name) { nameField.value = d.name; }
      if (d.email) { emailField.value = d.email; }
      document.getElementById('lookupInfo').textContent = d.last_id ? `ID: ${d.last_id} Visits: ${d.visits}` : '';
    }
  });
}
