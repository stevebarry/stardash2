import base64

import pytest

from app import create_app, export

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake").decode()


@pytest.fixture
def html():
    app = create_app()

    def render(items, title="Sales"):
        with app.test_request_context():
            return export.render_pdf_html(title, ["Region: North"], items, "alice")
    return render


def test_layout_keeps_widths_kpi_direction_and_numeric_columns(html):
    out = html([
        {"type": "kpi", "title": "Revenue", "value_text": "€1,000", "change_text": "▲ 5.0%", "dir": "up"},
        {"type": "chart", "title": "By month", "png": PNG, "width": "half"},
        {"type": "table", "title": "Top", "columns": ["Region", "Units"], "rows": [["North", "12"]],
         "numeric": [False, True], "width": "full"},
    ])
    assert 'class="kpi-change up"' in out
    assert 'class="card chart half"' in out and f'src="{PNG}"' in out
    assert 'class="card table-card full"' in out
    assert '<th>Region</th><th class="num">Units</th>' in out
    assert '<td>North</td><td class="num">12</td>' in out
    assert '<span class="chip">Region: North</span>' in out


def test_user_text_is_escaped_and_bad_images_dropped(html):
    out = html([{"type": "chart", "title": "<b>x</b>", "png": "http://evil/x.png"},
                {"type": "kpi", "title": "k", "value_text": "1", "dir": "sideways"}],
               title="<script>alert(1)</script>")
    assert "<script>alert" not in out and "&lt;script&gt;" in out
    assert "evil" not in out and "&lt;b&gt;x" not in out  # chart dropped entirely
    assert 'class="kpi-change' not in out  # no change text, invalid dir ignored


def test_long_tables_are_truncated_with_a_note(html):
    rows = [[str(i)] for i in range(export.MAX_EXPORT_ROWS + 20)]
    out = html([{"type": "table", "title": "All", "columns": ["N"], "rows": rows}])
    assert out.count("<td") == export.MAX_EXPORT_ROWS
    assert f"Showing the first {export.MAX_EXPORT_ROWS} of {export.MAX_EXPORT_ROWS + 20} rows." in out


def test_data_url_fetcher_refuses_other_urls():
    for url in ("http://169.254.169.254/latest", "file:///etc/passwd"):
        with pytest.raises(ValueError):
            export._data_urls_only(url)
