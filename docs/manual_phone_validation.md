# Manual Phone Validation Tests

Using the invite form with `intlTelInput` utils script loaded:

- `9876543210` (India local) → valid
- `+1 650-555-1234` (US international) → valid
- `123` → invalid
- `+99 12345` → invalid

These were confirmed in the browser console via `phoneInput.isValidNumber()`.
