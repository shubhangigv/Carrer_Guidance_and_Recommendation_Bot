from app import app


def test_chat_flow_over_http():
    client = app.test_client()
    r = client.post("/api/chat", json={"start": True})
    assert "name" in r.get_json()["reply"]
    for a in ["Rahul", "B.Com", "finance, business", "maths, accounting", "commerce, economics", "analytical"]:
        r = client.post("/api/chat", json={"message": a})
    data = r.get_json()
    assert data["done"]
    assert "Finance" in data["reply"]


def test_recommend_endpoint():
    client = app.test_client()
    r = client.post("/api/recommend", json={"interests": "law, debate", "skills": "public speaking, writing"})
    results = r.get_json()
    assert results[0]["title"] == "Lawyer"
    assert "roadmap" in results[0]


def test_index_and_careers():
    client = app.test_client()
    assert client.get("/").status_code == 200
    assert len(client.get("/api/careers").get_json()) >= 20
