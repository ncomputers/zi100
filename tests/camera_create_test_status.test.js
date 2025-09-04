/**
 * @jest-environment jsdom
 */

test('Next button requires successful test and resets on input change', async () => {
  document.body.innerHTML = `
    <div id="info">
      <input id="camName"><select id="camType"></select><input id="camUrl">
      <button id="testConn"></button>
      <button id="toPreview"></button>
      <div id="infoMessage"></div>
    </div>
    <div id="preview">
      <img id="previewImg">
      <div id="previewError"></div>
      <div id="previewMetrics"></div>
      <div id="previewActions">
        <button id="backInfo"></button>
        <button id="testConn"></button>
        <button id="toSettings"></button>
      </div>
    </div>
    <div id="settings">
      <button id="backPreview"></button>
      <button id="toReview"></button>
      <input id="setPPE"><input id="setVms"><input id="setFr"><input id="setCount">
      <select id="lineOrientation"></select>
      <input id="reverse"><input id="show">
    </div>
    <div id="review">
      <div id="reviewSummary"></div>
      <button id="backSettings"></button>
      <button id="confirmCam"></button>
    </div>
  `;

  global.bootstrap = {
    Tab: { getOrCreateInstance: () => ({ show: jest.fn() }) },
    Tooltip: jest.fn(),
  };

  global.fetch = jest
    .fn()
    .mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          ok: true,
          resolution: { width: 640, height: 480 },
          fps: 30,
          vendor: 'v',
        }),
    });

  const fs = require('fs');
  const path = require('path');
  const code = fs.readFileSync(path.resolve(__dirname, '../static/js/camera_create.js'), 'utf8');
  new Function(code)();
  document.dispatchEvent(new Event('DOMContentLoaded'));

  const toPreview = document.getElementById('toPreview');
  const confirmCam = document.getElementById('confirmCam');
  expect(toPreview.disabled).toBe(true);
  expect(confirmCam.disabled).toBe(true);

  const name = document.getElementById('camName');
  const url = document.getElementById('camUrl');
  name.value = 'test';
  url.value = 'http://example.com';
  name.dispatchEvent(new Event('input'));
  url.dispatchEvent(new Event('input'));

  const testConn = document.getElementById('testConn');
  testConn.click();
  await Promise.resolve();
  await Promise.resolve();
  expect(toPreview.disabled).toBe(false);

  url.value = 'http://changed.example.com';
  url.dispatchEvent(new Event('input'));
  expect(toPreview.disabled).toBe(true);
  expect(confirmCam.disabled).toBe(true);
});
