"""Export a dashboard to PDF (WeasyPrint) or Word (python-docx).

The browser sends already formatted content so the export matches the screen:
    kpi:   {type, title, value_text, change_text, previous_text, dir}   dir: up/down/flat
    chart: {type, title, png, width}               png is a data:image/png;base64 URL
    table: {type, title, columns, rows, numeric, width}  cells are display strings
width is "full" or "half"; numeric flags the right-aligned (measure) columns.
"""
import base64
import binascii
import io
from datetime import datetime

from docx import Document
from docx.shared import Pt
from flask import render_template

MAX_EXPORT_ROWS = 500
PNG_PREFIX = "data:image/png;base64,"


class ExportUnavailable(RuntimeError):
    """The server lacks the system libraries an export format needs."""


def _png_bytes(data_url):
    if not isinstance(data_url, str) or not data_url.startswith(PNG_PREFIX):
        return None
    try:
        return base64.b64decode(data_url[len(PNG_PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        return None


def _str(value):
    return "" if value is None else str(value)


def _table_cells(item):
    columns = [_str(c) for c in item.get("columns") or []]
    rows = [[_str(c) for c in row] for row in (item.get("rows") or [])[:MAX_EXPORT_ROWS]]
    return columns, rows


def _subtitle(username):
    return f"Exported {datetime.now():%Y-%m-%d %H:%M} by {username}"


def render_pdf_html(title, filter_lines, items, username):
    """HTML for the PDF export; split out of build_pdf so it can be tested without WeasyPrint."""
    kpis, widgets = [], []
    for item in items:
        kind = item.get("type")
        width = "half" if item.get("width") == "half" else "full"
        if kind == "kpi":
            kpis.append({"title": _str(item.get("title")), "value_text": _str(item.get("value_text")),
                         "change_text": _str(item.get("change_text")),
                         "previous_text": _str(item.get("previous_text")),
                         "dir": item.get("dir") if item.get("dir") in ("up", "down", "flat") else ""})
        elif kind == "chart":
            png = _png_bytes(item.get("png"))
            if png:
                widgets.append({"type": "chart", "title": _str(item.get("title")), "width": width,
                                "png": PNG_PREFIX + base64.b64encode(png).decode("ascii")})
        elif kind == "table":
            columns, rows = _table_cells(item)
            if not columns:
                continue
            numeric = [bool(n) for n in (item.get("numeric") or [])][:len(columns)]
            numeric += [False] * (len(columns) - len(numeric))
            total = len(item.get("rows") or [])
            widgets.append({"type": "table", "title": _str(item.get("title")), "width": width,
                            "columns": columns, "rows": rows, "numeric": numeric,
                            "total_rows": total, "truncated": total > len(rows)})
    return render_template("export_pdf.html", title=title, subtitle=_subtitle(username),
                           filter_lines=filter_lines, kpis=kpis, widgets=widgets)


def _data_urls_only(url, *args, **kwargs):
    """WeasyPrint URL fetcher: exports embed their images, so never reach out to the network or disk."""
    if not url.startswith("data:"):
        raise ValueError(f"Export refused to load {url!r}")
    from weasyprint import default_url_fetcher
    return default_url_fetcher(url, *args, **kwargs)


def build_pdf(title, filter_lines, items, username):
    try:
        from weasyprint import HTML
    except OSError as exc:  # Pango/GTK missing (e.g. on Windows)
        raise ExportUnavailable("PDF export needs the Pango libraries - see README") from exc
    html = render_pdf_html(title, filter_lines, items, username)
    buf = io.BytesIO(HTML(string=html, url_fetcher=_data_urls_only).write_pdf())
    buf.seek(0)
    return buf


def build_docx(title, filter_lines, items, username):
    doc = Document()
    section = doc.sections[0]
    usable_width = section.page_width - section.left_margin - section.right_margin
    doc.add_heading(title, level=0)
    p = doc.add_paragraph(_subtitle(username))
    p.runs[0].italic = True
    for line in filter_lines:
        doc.add_paragraph(line)

    kpis = [i for i in items if i.get("type") == "kpi"]
    if kpis:
        doc.add_heading("Key figures", level=1)
        table = doc.add_table(rows=1, cols=3)
        table.style = "Table Grid"
        for h, cell in zip(("KPI", "Value", "Change"), table.rows[0].cells):
            cell.text = h
            cell.paragraphs[0].runs[0].bold = True
        for k in kpis:
            cells = table.add_row().cells
            cells[0].text = _str(k.get("title"))
            cells[1].text = _str(k.get("value_text"))
            cells[2].text = f"{_str(k.get('change_text'))} {_str(k.get('previous_text'))}".strip()

    for item in items:
        kind = item.get("type")
        if kind == "chart":
            png = _png_bytes(item.get("png"))
            if not png:
                continue
            doc.add_heading(_str(item.get("title")), level=1)
            doc.add_picture(io.BytesIO(png), width=usable_width)
        elif kind == "table":
            columns, rows = _table_cells(item)
            if not columns:
                continue
            doc.add_heading(_str(item.get("title")), level=1)
            table = doc.add_table(rows=1, cols=len(columns))
            table.style = "Table Grid"
            for h, cell in zip(columns, table.rows[0].cells):
                cell.text = h
                cell.paragraphs[0].runs[0].bold = True
            for row in rows:
                for value, cell in zip(row, table.add_row().cells):
                    cell.text = value
            for row in table.rows:
                for cell in row.cells:
                    for para in cell.paragraphs:
                        for run in para.runs:
                            run.font.size = Pt(8)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
