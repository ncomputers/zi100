/**
 * @jest-environment jsdom
 */

const fs = require('fs');
const path = require('path');

describe('face_db_source permissions', () => {
  let initSource, start;

  function setupDom() {
    document.body.innerHTML = `
      <select id="sourceSelect"><option value="browser">Browser</option></select>
      <video id="liveVideo"></video>
      <canvas id="cameraCanvas"></canvas>
      <canvas id="overlayCanvas"></canvas>
      <canvas id="captureCanvas"></canvas>
      <div id="liveFaceInfo"></div>
      <input id="scaleFactor" value="1.1" />
      <input id="minNeighbors" value="3" />
      <input id="recThreshold" value="0.5" />
      <span id="scaleVal"></span>
      <span id="neighborVal"></span>
      <span id="recThreshVal"></span>
      <button id="startCameraBtn"></button>
      <div id="cameraError"></div>
    `;
  }

  function loadModule() {
    let code = fs.readFileSync(
      path.resolve(__dirname, '../static/js/face_db_source.js'),
      'utf8'
    );
    code = code
      .replace(/export function initSource/, 'function initSource')
      .replace(/export async function start/, 'async function start')
      .replace(/export function stop/, 'function stop');
    code += '\nwindow.__fdb = { initSource, start };';
    new Function(code)();
    ({ initSource, start } = window.__fdb);
  }

  beforeEach(() => {
    setupDom();
    jest.resetModules();
    Object.defineProperty(window, 'navigator', {
      value: { mediaDevices: {}, permissions: {} },
      configurable: true
    });
    loadModule();
  });

  test('start enabled when permission prompt', async () => {
    navigator.permissions.query = jest.fn(() =>
      Promise.resolve({ state: 'prompt', onchange: null })
    );
    initSource();
    await Promise.resolve();
    const btn = document.getElementById('startCameraBtn');
    expect(btn.disabled).toBe(false);
  });

  test('controls disabled when permission denied', async () => {
    navigator.permissions.query = jest.fn(() =>
      Promise.resolve({ state: 'denied', onchange: null })
    );
    initSource();
    await Promise.resolve();
    const btn = document.getElementById('startCameraBtn');
    const msg = document.getElementById('cameraError').textContent;
    expect(btn.disabled).toBe(true);
    expect(msg).toMatch(/re-enable it in your browser settings/i);
  });

  test('getUserMedia errors surface to UI', async () => {
    navigator.permissions.query = jest.fn(() =>
      Promise.resolve({ state: 'granted', onchange: null })
    );
    const err = new Error('denied');
    err.name = 'NotAllowedError';
    navigator.mediaDevices.getUserMedia = jest.fn(() => Promise.reject(err));
    initSource();
    await Promise.resolve();
    await start();
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalled();
    const msg = document.getElementById('cameraError').textContent;
    expect(msg).toMatch(/Camera access was denied/);
  });
});
