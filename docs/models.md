# Models

Detection models are loaded through the [model registry](../modules/model_registry.py).

* Configure model paths in [config.json](../config.json) under `person_model` and `ppe_model`.
* Models typically use the YOLOv8 architecture for person and PPE detection.

## Face detection weights

Front-end face detection relies on the [face-api.js](https://github.com/justadudewhohacks/face-api.js) tiny face detector.

The app loads `tiny_face_detector_model-weights_manifest.json` and `tiny_face_detector_model-shard1` directly from
`https://raw.githubusercontent.com/ncomputers/faceModal_1/main/`, so no local downloads are required. The front-end
loader fetches the weights with:

```javascript
await faceapi.nets.tinyFaceDetector.loadFromUri('https://raw.githubusercontent.com/ncomputers/faceModal_1/main/');
```
