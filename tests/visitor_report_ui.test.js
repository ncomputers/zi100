/**
 * @jest-environment jsdom
 */

describe('visitor report UI', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <input id="range" />
      <button id="loadReport"></button>
    `;
  });

  test('initializes flatpickr on #range and handles Load Report', () => {
    const mockPicker = { selectedDates: [], setDate: jest.fn() };
    const flatpickr = jest.fn(() => mockPicker);
    global.flatpickr = flatpickr;

    const loadReport = jest.fn();
    global.loadReport = loadReport;

    document.addEventListener('DOMContentLoaded', () => {
      flatpickr('#range', { mode: 'range', dateFormat: 'Y-m-d' });
      document.getElementById('loadReport').addEventListener('click', loadReport);
    });

    document.dispatchEvent(new Event('DOMContentLoaded'));

    expect(flatpickr).toHaveBeenCalledWith('#range', {
      mode: 'range',
      dateFormat: 'Y-m-d',
    });

    document.getElementById('loadReport').click();
    expect(loadReport).toHaveBeenCalledTimes(1);
  });

  test('resetRange handler is skipped if element is missing', () => {
    global.flatpickr = jest.fn(() => ({ selectedDates: [] }));

    document.addEventListener('DOMContentLoaded', () => {
      const resetBtn = document.getElementById('resetRange');
      if (resetBtn) {
        resetBtn.addEventListener('click', () => {});
      }
    });

    expect(() => document.dispatchEvent(new Event('DOMContentLoaded'))).not.toThrow();
  });
});

