def test_home_endpoint(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "status": "healthy"
    }


def test_database_health_endpoint(client):
    response = client.get("/health/database")

    assert response.status_code == 200

    body = response.get_json()

    assert body["success"] is True
    assert body["database"] == "connected"
