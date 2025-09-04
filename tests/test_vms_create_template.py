import pytest


def test_visitor_tab_has_labels(client):
    from config import config as cfg

    cfg.setdefault("features", {})["visitor_mgmt"] = True
    r = client.get("/vms/create")
    assert r.status_code == 200
    html = r.text
    start = html.index('id="visitor"')
    end = html.index('id="photo"')
    visitor_html = html[start:end]
    # No floating labels in visitor tab
    assert "form-floating" not in visitor_html
    for field in [
        "inviteId",
        "vName",
        "vPhone",
        "vEmail",
        "vType",
        "vPurpose",
        "vCompany",
        "vValid",
    ]:
        assert f'label for="{field}"' in visitor_html


def test_preview_controls_marked_no_print(client):
    from config import config as cfg

    cfg.setdefault("features", {})["visitor_mgmt"] = True
    r = client.get("/vms/create")
    assert r.status_code == 200
    html = r.text
    assert 'id="printBtn"' in html
    before = html.rsplit('id="printBtn"', 1)[0]
    div_start = before.rfind("<div")
    div_end = html.find(">", div_start)
    assert "no-print" in html[div_start:div_end]
