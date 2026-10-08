import pytest
from httpx import ASGITransport, AsyncClient

from app.channels.registry import register
from app.main import app
from app.models import Channel
from tests.fakes import FakeAdapter


class FakeArq:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, name, *args):
        self.jobs.append((name, args))


@pytest.fixture
async def client():
    app.state.arq = FakeArq()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_create_search_enqueues_job(client):
    register(FakeAdapter(Channel.REDDIT))
    register(FakeAdapter(Channel.TIKTOK))

    r = await client.post("/searches", json={"keyword": "  camping   chair ", "depth": "light"})

    assert r.status_code == 202
    body = r.json()
    assert body["keyword"] == "camping chair"
    assert body["channels"] == ["reddit", "tiktok"]
    assert body["status"] == "queued"
    assert app.state.arq.jobs == [("run_search_job", (body["id"],))]

    r = await client.get(f"/searches/{body['id']}")
    assert r.status_code == 200
    assert (await client.get("/searches")).json()[0]["id"] == body["id"]


async def test_rejects_unregistered_channel(client):
    register(FakeAdapter(Channel.REDDIT))

    r = await client.post("/searches", json={"keyword": "camping chair", "channels": ["reddit", "instagram"]})

    assert r.status_code == 422
    assert "instagram" in r.json()["detail"]
    assert app.state.arq.jobs == []


async def test_validation(client):
    register(FakeAdapter(Channel.REDDIT))
    assert (await client.post("/searches", json={"keyword": "x"})).status_code == 422
    assert (await client.post("/searches", json={"keyword": "chair", "depth": "huge"})).status_code == 422
    assert (await client.post("/searches", json={"keyword": "chair", "channels": []})).status_code == 422


async def test_unknown_search_404(client):
    r = await client.get("/searches/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
