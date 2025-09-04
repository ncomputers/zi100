# modules_export
[Back to Architecture Overview](../README.md)

## Purpose
Purpose: Export module.

## Key Classes
None

## Key Functions
- **export_csv(data, columns, filename)** - Export rows as CSV and return StreamingResponse.
- **export_excel(data, columns, filename, image_key, image_label="Image")** - Export rows as XLSX with an optional image column and customizable header label.
- **export_pdf(html_content, filename)** - Render HTML to PDF using WeasyPrint.
  Assets like CSS and images are resolved relative to the project root so they
  appear correctly in the generated PDF.

## Inputs and Outputs
Refer to function signatures above for inputs and outputs.

## Redis Keys
None

## Dependencies
- __future__
- csv
- fastapi.responses
- io
- loguru
- pathlib
- typing
