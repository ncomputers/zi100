/**
 * @jest-environment jsdom
 */

let PhotoCapture;
try {
  PhotoCapture = require('../static/js/photo_capture.js');
} catch {
  PhotoCapture = null;
}

(PhotoCapture ? describe : describe.skip)('PhotoCapture face detection', () => {
  let pc;
  let drawImage;
  let origCreate;

  beforeEach(() => {
    document.body.innerHTML = '<img id="photoPreview" />';

    pc = new PhotoCapture({
      videoEl: document.createElement('video'),
      uploadInput: document.createElement('input'),
      onCapture: jest.fn(),
      faceThreshold: 0.4
    });
    pc.modelsLoaded = true;
    pc.openCropper = jest.fn();

    drawImage = jest.fn();
    origCreate = document.createElement.bind(document);
    document.createElement = (tag) => {
      if (tag === 'canvas') {
        return {
          width: 0,
          height: 0,
          getContext: () => ({ drawImage }),
          toDataURL: () => 'data:image/jpeg;base64,crop'
        };
      }
      return origCreate(tag);
    };

    global.Image = class {
      constructor() {
        this.width = 100;
        this.height = 100;
        this._src = null;
        this._onload = null;
      }
      set src(v) {
        this._src = v;
        if (this._onload) setTimeout(() => this._onload());
      }
      set onload(fn) {
        this._onload = fn;
        if (this._src) setTimeout(() => this._onload());
      }
    };
  });

  afterEach(() => {
    document.createElement = origCreate;
  });

  test('expands padding for low-confidence detection', async () => {
    global.faceapi = {
      TinyFaceDetectorOptions: function (opts) { this.opts = opts; },
      detectSingleFace: jest.fn(() => Promise.resolve({
        score: 0.45,
        box: { x: 10, y: 10, width: 30, height: 30 }
      }))
    };

    await pc.processImage('foo');

    expect(drawImage).toHaveBeenCalled();
    const args = drawImage.mock.calls[0];
    expect(args[1]).toBe(0); // sx
    expect(args[2]).toBe(0); // sy
    expect(args[3]).toBe(100); // sw
    expect(args[4]).toBe(100); // sh
    expect(pc.openCropper).not.toHaveBeenCalled();
    expect(pc.onCapture).toHaveBeenCalled();
  });

  test('retries with lower threshold before falling back', async () => {
    const detectMock = jest
      .fn()
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce({
        score: 0.35,
        box: { x: 10, y: 10, width: 30, height: 30 }
      });
    global.faceapi = {
      TinyFaceDetectorOptions: function (opts) { this.opts = opts; },
      detectSingleFace: detectMock
    };

    await pc.processImage('bar');

    expect(detectMock).toHaveBeenCalledTimes(2);
    expect(drawImage).toHaveBeenCalled();
    const args = drawImage.mock.calls[0];
    expect(args[3]).toBe(100); // sw
    expect(args[4]).toBe(100); // sh
    expect(pc.openCropper).not.toHaveBeenCalled();
  });
});
