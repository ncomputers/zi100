(() => {
  const metricOptions = document.getElementById('metricOptionsTemplate').innerHTML;

  function rowTemplate() {
    return `<tr>
    <td><select class="form-select metric">${metricOptions}</select></td>
    <td><select class="form-select type"><option value="event">Event</option><option value="threshold">Threshold</option><option value="frequency">Frequency</option></select></td>
    <td><input type="number" class="form-control value" value="1"></td>
    <td><input class="form-control recipients"></td>
    <td class="text-center"><input type="checkbox" class="form-check-input attach"></td>
    <td><button class="btn btn-danger btn-sm del">Delete</button></td>
  </tr>`;
  }

  document.getElementById('addRule').onclick = function () {
    document.querySelector('#rulesTable tbody').insertAdjacentHTML('beforeend', rowTemplate());
  };

  document.querySelector('#rulesTable').addEventListener('click', e => {
    if (e.target.classList.contains('del')) e.target.closest('tr').remove();
  });

  document.getElementById('save').onclick = async () => {
    const rows = document.querySelectorAll('#rulesTable tbody tr');
    const rules = [];
    rows.forEach(r => {
      rules.push({
        metric: r.querySelector('.metric').value,
        type: r.querySelector('.type').value,
        value: parseInt(r.querySelector('.value').value || 0),
        recipients: r.querySelector('.recipients').value,
        attach: r.querySelector('.attach').checked
      });
    });
    const r = await fetch('/alerts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rules })
    });
    const d = await r.json();
    document.getElementById('msg').innerHTML = d.saved ? '<div class="alert alert-success">Saved</div>' : '<div class="alert alert-danger">Error</div>';
  };
})();
