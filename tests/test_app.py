from teky.app import app


def test_home_route():
    client = app.test_client()
    rv = client.get("/")
    assert rv.status_code == 200
    assert b"WiFi Drone Control Web App" in rv.data
