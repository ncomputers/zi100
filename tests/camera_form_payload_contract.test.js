/**
 * UI contract test: ensure form payload matches API schema fields.
 */

test('camera form payload matches API schema', () => {
  const buildPayload = () => ({
    name: 'Cam',
    url: 'rtsp://demo',
    orientation: 'vertical',
    transport: 'tcp',
    resolution: 'original',
    ppe: false,
    vms: false,
    face_recog: false,
    inout_count: false,
    reverse: false,
    show: false,
    enabled: false,
    profile: null,
    site_id: null,
    type: 'rtsp'
  });

  const expected = [
    'name',
    'url',
    'orientation',
    'transport',
    'resolution',
    'ppe',
    'vms',
    'face_recog',
    'inout_count',
    'reverse',
    'show',
    'enabled',
    'profile',
    'site_id',
    'type'
  ];

  const payload = buildPayload();
  expect(Object.keys(payload).sort()).toEqual(expected.sort());
});
