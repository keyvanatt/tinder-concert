import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_user(client, name, genres=""):
    return client.post("/users", json={"name": name, "genres": genres}).json()["id"]


def make_concert(client):
    return client.post(
        "/concerts",
        json={"artist": "Daft Punk", "venue": "Bercy", "city": "Paris",
              "date": "2026-12-01T20:00:00Z"},
    ).json()["id"]


def attend(client, concert, user, size):
    r = client.post(f"/concerts/{concert}/attend", json={"user_id": user, "group_size": size})
    assert r.status_code == 201, r.text


def like(client, concert, a, b, liked=True):
    r = client.post(f"/concerts/{concert}/swipes",
                    json={"swiper_id": a, "target_id": b, "liked": liked})
    assert r.status_code == 201, r.text
    return r.json()


def test_duo_forms_on_mutual_like(client):
    c = make_concert(client)
    a, b = make_user(client, "Alice"), make_user(client, "Bob")
    attend(client, c, a, 2)
    attend(client, c, b, 2)

    assert like(client, c, a, b) == {"mutual": False, "group": None}
    result = like(client, c, b, a)
    assert result["mutual"] is True
    assert [m["name"] for m in result["group"]["members"]] == ["Alice", "Bob"]

    # Une fois groupés, on ne les propose plus et ils ne swipent plus
    assert client.get(f"/concerts/{c}/feed", params={"user_id": a}).json() == []
    assert len(client.get(f"/users/{a}/groups").json()) == 1


def test_trio_needs_everyone_to_like_each_other(client):
    c = make_concert(client)
    a, b, d = (make_user(client, n) for n in ("A", "B", "D"))
    for u in (a, b, d):
        attend(client, c, u, 3)

    like(client, c, a, b)
    assert like(client, c, b, a) == {"mutual": True, "group": None}
    like(client, c, a, d)
    like(client, c, d, a)
    like(client, c, b, d)
    result = like(client, c, d, b)
    assert sorted(m["id"] for m in result["group"]["members"]) == sorted([a, b, d])


def test_feed_filters_and_orders(client):
    c = make_concert(client)
    me = make_user(client, "Me", "rock,electro")
    fan = make_user(client, "Fan", "jazz")
    rocker = make_user(client, "Rocker", "Rock, electro")
    other_size = make_user(client, "Quatuor")
    stranger = make_user(client, "Stranger")
    attend(client, c, me, 2)
    attend(client, c, fan, 2)
    attend(client, c, rocker, 2)
    attend(client, c, stranger, 2)
    attend(client, c, other_size, 4)

    like(client, c, fan, me)  # Fan m'a liké : il passe devant
    like(client, c, me, stranger, liked=False)  # déjà swipé : disparaît

    feed = client.get(f"/concerts/{c}/feed", params={"user_id": me}).json()
    assert [u["name"] for u in feed] == ["Fan", "Rocker"]


def test_swipe_validations(client):
    c = make_concert(client)
    a, b, d = (make_user(client, n) for n in ("A", "B", "D"))
    attend(client, c, a, 2)
    attend(client, c, b, 3)

    def swipe(x, y):
        return client.post(f"/concerts/{c}/swipes",
                           json={"swiper_id": x, "target_id": y, "liked": True})

    assert swipe(a, a).status_code == 400
    assert swipe(a, d).status_code == 404  # D ne va pas au concert
    assert swipe(a, b).status_code == 409  # tailles différentes
    assert client.post(f"/concerts/{c}/attend",
                       json={"user_id": a, "group_size": 2}).status_code == 409
    assert client.post(f"/concerts/{c}/attend",
                       json={"user_id": d, "group_size": 5}).status_code == 422


def test_group_chat_is_members_only(client):
    c = make_concert(client)
    a, b, intruder = (make_user(client, n) for n in ("A", "B", "X"))
    attend(client, c, a, 2)
    attend(client, c, b, 2)
    like(client, c, a, b)
    group_id = like(client, c, b, a)["group"]["id"]

    r = client.post(f"/groups/{group_id}/messages",
                    json={"user_id": a, "content": "On se retrouve au bar avant ?"})
    assert r.status_code == 201
    msgs = client.get(f"/groups/{group_id}/messages", params={"user_id": b}).json()
    assert [m["content"] for m in msgs] == ["On se retrouve au bar avant ?"]
    assert client.get(f"/groups/{group_id}/messages",
                      params={"user_id": intruder}).status_code == 403
