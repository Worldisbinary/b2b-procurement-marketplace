import pytest


@pytest.fixture()
def two_suppliers(all_products):
    """Two products from different suppliers, both with moq."""
    a = all_products[0]
    b = next(p for p in all_products if p["supplier_id"] != a["supplier_id"])
    return a, b


def make_rfq(client, *products, extra=0):
    items = [{"product_id": p["id"], "qty": p["moq"] + extra} for p in products]
    r = client.post("/rfqs", json={"buyer": "Acme Ltd", "items": items})
    assert r.status_code == 201, r.text
    return r.json()


def quote(client, rfq, product, supplier_id=None, price=1.5):
    item = next(i for i in rfq["items"] if i["product_id"] == product["id"])
    r = client.post(
        f"/rfqs/{rfq['id']}/quotes",
        json={"supplier_id": supplier_id or product["supplier_id"],
              "lines": [{"rfq_item_id": item["id"], "unit_price": price}]},
    )
    return r


def status(client, rfq_id):
    return client.get(f"/rfqs/{rfq_id}").json()["status"]


def test_create_rfq_ok(client, two_suppliers):
    rfq = make_rfq(client, *two_suppliers)
    assert rfq["status"] == "open" and len(rfq["items"]) == 2


def test_create_rfq_below_moq_rejected(client, all_products):
    p = next(p for p in all_products if p["moq"] > 1)
    r = client.post("/rfqs", json={"buyer": "X", "items": [{"product_id": p["id"], "qty": p["moq"] - 1}]})
    assert r.status_code == 422


def test_create_rfq_validation(client):
    assert client.post("/rfqs", json={"buyer": "X", "items": []}).status_code == 422
    assert client.post("/rfqs", json={"buyer": "X", "items": [{"product_id": 999999, "qty": 5}]}).status_code == 404
    assert client.post("/rfqs", json={"buyer": "X", "items": [{"product_id": 1, "qty": 0}]}).status_code == 422


def test_quote_moves_rfq_to_quoted(client, two_suppliers):
    a, b = two_suppliers
    rfq = make_rfq(client, a, b)
    r = quote(client, rfq, a)
    assert r.status_code == 201 and r.json()["status"] == "submitted"
    assert status(client, rfq["id"]) == "quoted"


def test_quote_for_foreign_product_rejected(client, two_suppliers):
    a, b = two_suppliers
    rfq = make_rfq(client, a)
    assert quote(client, rfq, a, supplier_id=b["supplier_id"]).status_code == 422


def test_accept_rejects_other_quotes_and_awards(client, two_suppliers):
    a, b = two_suppliers
    rfq = make_rfq(client, a, b)
    q1 = quote(client, rfq, a).json()
    q2 = quote(client, rfq, b).json()
    r = client.post(f"/quotes/{q1['id']}/accept")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "awarded"
    states = {q["id"]: q["status"] for q in body["quotes"]}
    assert states == {q1["id"]: "accepted", q2["id"]: "rejected"}


def test_cannot_accept_twice_or_accept_rejected(client, two_suppliers):
    a, b = two_suppliers
    rfq = make_rfq(client, a, b)
    q1 = quote(client, rfq, a).json()
    q2 = quote(client, rfq, b).json()
    assert client.post(f"/quotes/{q1['id']}/accept").status_code == 200
    assert client.post(f"/quotes/{q1['id']}/accept").status_code == 409
    assert client.post(f"/quotes/{q2['id']}/accept").status_code == 409
    assert client.post(f"/quotes/{q1['id']}/reject").status_code == 409


def test_reject_then_accept_is_conflict(client, two_suppliers):
    a, _ = two_suppliers
    rfq = make_rfq(client, a)
    q = quote(client, rfq, a).json()
    assert client.post(f"/quotes/{q['id']}/reject").json()["status"] == "rejected"
    assert client.post(f"/quotes/{q['id']}/accept").status_code == 409
    assert client.post(f"/quotes/{q['id']}/reject").status_code == 409
    assert status(client, rfq["id"]) == "quoted"


def test_no_quotes_on_awarded_or_closed_rfq(client, two_suppliers):
    a, _ = two_suppliers
    rfq = make_rfq(client, a)
    q = quote(client, rfq, a).json()
    client.post(f"/quotes/{q['id']}/accept")
    assert quote(client, rfq, a).status_code == 409
    rfq2 = make_rfq(client, a)
    assert client.post(f"/rfqs/{rfq2['id']}/close").json()["status"] == "closed"
    assert quote(client, rfq2, a).status_code == 409


def test_close_transitions(client, two_suppliers):
    a, _ = two_suppliers
    rfq = make_rfq(client, a)
    q = quote(client, rfq, a).json()
    closed = client.post(f"/rfqs/{rfq['id']}/close").json()
    assert closed["status"] == "closed" and closed["quotes"][0]["status"] == "rejected"
    assert client.post(f"/rfqs/{rfq['id']}/close").status_code == 409
    assert client.post(f"/quotes/{q['id']}/accept").status_code == 409


def test_not_found(client):
    assert client.get("/rfqs/999999").status_code == 404
    assert client.post("/quotes/999999/accept").status_code == 404
    assert client.post("/rfqs/999999/close").status_code == 404
