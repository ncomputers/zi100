from bs4 import BeautifulSoup


def test_admin_users_template_renders(client):
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    soup = BeautifulSoup(resp.text, "html.parser")
    assert soup.select_one("#inviteBtn") is not None
    assert soup.select_one("#exportBtn") is not None
    assert soup.select_one("#inviteDrawer") is not None
