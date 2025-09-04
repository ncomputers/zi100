/**
 * @jest-environment jsdom
 */

const fs = require('fs');
const path = require('path');

function loadScript() {
  let code = fs.readFileSync(
    path.resolve(__dirname, '../static/js/camera_create.js'),
    'utf8',
  );
  code = code.replace(
    'const probeMetrics = async () =>',
    'window.probeMetrics = async () =>',
  );
  new Function(code)();
  document.dispatchEvent(new Event('DOMContentLoaded'));
}

function setupDom() {
  document.body.innerHTML = `
    <div id="info">
      <input id="camName"><select id="camType"></select><input id="camUrl">
      <input id="camLocation"><input id="camUsername"><input id="camPassword"><select id="camRes"></select>
      <input id="camFps"><input id="camStreamType">
      <button id="testConn"></button>
      <div id="infoMessage"></div>
    </div>
    <div id="preview">
      <img id="previewImg">
      <div id="previewError"></div>
      <div id="previewMetrics"></div>
      <div id="previewActions"><button id="backInfo"></button><button id="toSettings"></button></div>
      <button id="testConn"></button>
    </div>
    <button id="toPreview"></button>
    <button id="backPreview"></button>
    <button id="toReview"></button>
    <button id="backSettings"></button>
    <button id="confirmCam"></button>
    <div id="reviewSummary"></div>
    <input id="setPPE"><input id="setVms"><input id="setFr"><input id="setCount">
    <select id="lineOrientation"></select>
    <input id="reverse">
    <input id="show">
  `;
  global.bootstrap = { Tab: { getOrCreateInstance: () => ({ show: jest.fn() }) }, Tooltip: jest.fn() };
  global.setInterval = jest.fn();
  global.clearInterval = jest.fn();
}

test('renders metrics on successful probe', async () => {
  setupDom();
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: true,
    json: () =>
      Promise.resolve({
        metadata: { codec: 'h264', width: 640, height: 480 },
        effective_fps: 30,
        transport: 'tcp',
        hwaccel: false,
      }),
  });
  loadScript();
  await window.probeMetrics();
  expect(document.getElementById('previewMetrics').textContent).toContain('Codec: h264');
});

test.each([
  [401, 'Authentication failed'],
  [500, 'Unsupported codec'],
])('shows probe error for status %i', async (status, message) => {
  setupDom();
  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: false,
    status,
    json: () => Promise.resolve({ error: message }),
  });
  loadScript();
  await window.probeMetrics();
  expect(document.getElementById('previewMetrics').textContent).toBe(message);
});
