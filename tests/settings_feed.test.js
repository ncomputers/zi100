/**
 * @jest-environment jsdom
 */

global.__TEST__ = true;
const { getLastPathSegment } = require('../static/js/settings.js');

describe('getLastPathSegment', () => {
  test('handles relative URLs', () => {
    expect(getLastPathSegment('/stream/cam1')).toBe('cam1');
    expect(getLastPathSegment('stream/cam4')).toBe('cam4');
  });

  test('handles absolute URLs', () => {
    expect(getLastPathSegment('http://example.com/stream/cam2')).toBe('cam2');
  });

  test('handles query parameters', () => {
    expect(getLastPathSegment('/stream/cam3?raw=1')).toBe('cam3');
  });
});
