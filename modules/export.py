"""Helpers for exporting data to CSV and other formats."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable, Mapping

from fastapi.responses import FileResponse, StreamingResponse
from loguru import logger

ROOT_DIR = Path(__file__).resolve().parent.parent
EXPORT_DIR = ROOT_DIR / "static" / "exports"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


# export_csv routine
def export_csv(data: Iterable[Mapping], columns: list[tuple[str, str]], filename: str):
    """Export rows as CSV and return StreamingResponse."""
    rows = list(data)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([row.get(key, "") for key, _ in columns])
    path = EXPORT_DIR / f"{filename}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write(output.getvalue())
    output.seek(0)
    headers = {"Content-Disposition": f"attachment; filename={path.name}"}
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode()), media_type="text/csv", headers=headers
    )


# export_excel routine
def export_excel(
    data: Iterable[Mapping],
    columns: list[tuple[str, str]],
    filename: str,
    image_key: str | None = None,
    image_label: str = "Image",
):
    """Export rows as XLSX with optional image column."""
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage

    rows = list(data)
    wb = Workbook()
    ws = wb.active
    headers = [label for _, label in columns]
    if image_key:
        headers.append(image_label)
    ws.append(headers)
    for row in rows:
        ws.append([row.get(key, "") for key, _ in columns])
        if image_key:
            img_path = row.get(image_key)
            if img_path and Path(img_path).exists():
                try:
                    img = XLImage(img_path)
                    img.width = 80
                    img.height = 60
                    ws.add_image(img, f'{chr(ord("A")+len(columns))}{ws.max_row}')
                except Exception as exc:
                    logger.exception("Failed to add image {}: {}", img_path, exc)
    path = EXPORT_DIR / f"{filename}.xlsx"
    wb.save(path)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


# export_pdf routine
def export_pdf(html_content: str, filename: str):
    """Render HTML to PDF using WeasyPrint.

    Resources such as CSS, logos and photos are resolved relative to the
    project's root directory, allowing exported PDFs to correctly include
    those assets regardless of the execution path.
    """
    try:
        from weasyprint import HTML, default_url_fetcher

        path = EXPORT_DIR / f"{filename}.pdf"
        # Resolve project root based on this file's location so asset paths
        # remain valid even if the current working directory changes.
        base_url = str(Path(__file__).resolve().parent.parent)

        def url_fetcher(url: str):
            from urllib.parse import urlsplit

            path_part = urlsplit(url).path
            resource_path = path_part.lstrip("/")
            if resource_path.startswith(("static/", "logos/")):
                local_path = Path(base_url) / resource_path
                return default_url_fetcher(local_path.as_uri())
            return default_url_fetcher(url)

        HTML(
            string=html_content,
            base_url=base_url,
            url_fetcher=url_fetcher,
        ).write_pdf(path)
    except Exception as exc:  # capture missing deps and other failures
        msg = f"pdf_unavailable: {exc}"
        logger.exception("PDF export failed: {}", exc)
        return {"error": msg}
    return FileResponse(path, media_type="application/pdf", filename=path.name)
