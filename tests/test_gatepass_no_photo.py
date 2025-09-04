import fakeredis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import gatepass
from routers.gatepass import create


def test_gatepass_create_no_photo(tmp_path):
    cfg = {"features": {"visitor_mgmt": True}}
    r = fakeredis.FakeRedis(decode_responses=True)
    (tmp_path / "gatepass_print.html").write_text("tmpl")
    gatepass.init_context(cfg, r, str(tmp_path))
    create.save_base64_to_image = lambda *a, **k: "img.jpg"
    create.add_face_to_known_db = lambda **k: None
    create._send_pdf_email = lambda *a, **k: None
    app = FastAPI()
    app.post("/gatepass/create")(create.gatepass_create)
    client = TestClient(app)
    resp = client.post(
        "/gatepass/create",
        data={
            "name": "Bob",
            "phone": "1234567890",
            "email": "",
            "host": "Alice",
            "purpose": "Visit",
            "visitor_type": "Official",
            "host_department": "IT",
            "company_name": "Acme Corp",
            "valid_to": "2030-01-01 00:00",
            "approver_email": "",
            "captured": "",
            "no_photo": "on",
        },
    )
    assert resp.status_code == 200
    gate_id = resp.json()["gate_id"]
    rec = r.hgetall(f"gatepass:pass:{gate_id}")
    assert "image" not in rec
    assert rec.get("no_photo") == "True"
