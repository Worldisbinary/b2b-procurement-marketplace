def get(client, **params):
    r = client.get("/products", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def walk(client, **params):
    """Follow cursors to the end; return all items in order."""
    items, cursor, pages = [], None, 0
    while True:
        p = dict(params, limit=70)
        if cursor:
            p["cursor"] = cursor
        data = get(client, **p)
        items += data["items"]
        pages += 1
        cursor = data["next_cursor"]
        if not cursor:
            return items, pages


def test_seed_has_1000_products(client, all_products):
    assert len(all_products) == 1000
    items, _ = walk(client)
    assert len(items) == 1000


def test_keyword_search_case_insensitive(client, all_products):
    expected = {p["id"] for p in all_products if "gloves" in (p["name"] + p["description"]).lower()}
    assert expected
    for q in ("gloves", "GLOVES", "GlOvEs"):
        items, _ = walk(client, q=q)
        assert {i["id"] for i in items} == expected


def test_category_and_price_range(client, all_products):
    expected = {p["id"] for p in all_products if p["category"] == "Tools" and 20 <= p["price"] <= 100}
    assert expected
    items, _ = walk(client, category="Tools", min_price=20, max_price=100)
    assert {i["id"] for i in items} == expected
    assert all(i["category"] == "Tools" and 20 <= i["base_price"] <= 100 for i in items)


def test_in_stock_filter(client, all_products):
    expected = {p["id"] for p in all_products if p["stock"] > 0}
    assert len(expected) < 1000
    items, _ = walk(client, in_stock="true")
    assert {i["id"] for i in items} == expected


def test_supplier_filter(client, all_products):
    sid = all_products[0]["supplier_id"]
    items, _ = walk(client, q="")
    name = next(i["supplier"] for i in items if i["id"] == all_products[0]["id"])
    got, _ = walk(client, supplier=name)
    assert {i["id"] for i in got} == {p["id"] for p in all_products if p["supplier_id"] == sid}


def test_sort_price_asc_and_desc(client, all_products):
    asc, _ = walk(client, sort="price")
    assert [i["id"] for i in asc] == [p["id"] for p in sorted(all_products, key=lambda p: (p["price"], p["id"]))]
    desc, _ = walk(client, sort="price_desc")
    assert [i["id"] for i in desc] == [
        p["id"] for p in sorted(all_products, key=lambda p: (p["price"], p["id"]), reverse=True)
    ]


def test_sort_name(client, all_products):
    items, _ = walk(client, sort="name")
    names = [i["name"] for i in items]
    assert names == sorted(names)


def test_sort_newest(client):
    items, _ = walk(client, sort="newest")
    ids = [i["id"] for i in items]
    assert ids == sorted(ids, reverse=True)


def test_pagination_no_duplicates_or_gaps(client):
    for sort in ("price", "price_desc", "name", "newest"):
        items, pages = walk(client, sort=sort)
        ids = [i["id"] for i in items]
        assert pages > 1
        assert len(ids) == len(set(ids)) == 1000
        assert set(ids) == set(range(1, 1001))


def test_pagination_with_filter_and_page_size(client, all_products):
    data = get(client, category="Fasteners", limit=5, sort="price")
    assert len(data["items"]) == 5 and data["next_cursor"]
    items, _ = walk(client, category="Fasteners", sort="price")
    assert len(items) == len({i["id"] for i in items}) == sum(p["category"] == "Fasteners" for p in all_products)


def test_last_page_has_no_cursor(client):
    assert get(client, limit=100, category="Tools", min_price=0)["items"]
    data = get(client, q="Gloves", limit=100)
    assert data["next_cursor"] is None


def test_empty_result(client):
    data = get(client, q="no-such-product-xyz")
    assert data == {"items": [], "next_cursor": None}
    assert get(client, min_price=999999)["items"] == []


def test_invalid_cursor_and_sort_mismatch(client):
    assert client.get("/products", params={"cursor": "garbage"}).status_code == 400
    cur = get(client, sort="price", limit=5)["next_cursor"]
    assert client.get("/products", params={"cursor": cur, "sort": "name"}).status_code == 400


def test_limit_validation(client):
    assert client.get("/products", params={"limit": 0}).status_code == 422
    assert client.get("/products", params={"limit": 1000}).status_code == 422


def test_product_detail_with_tiers(client, all_products):
    p = all_products[0]
    r = client.get(f"/products/{p['id']}")
    assert r.status_code == 200
    assert [(t["min_qty"], t["unit_price"]) for t in r.json()["tiers"]] == p["tiers"]
    assert client.get("/products/999999").status_code == 404


def test_price_endpoint(client, all_products):
    p = next(p for p in all_products if len(p["tiers"]) >= 2)
    min_qty, tier_price = p["tiers"][1]
    r = client.get(f"/products/{p['id']}/price", params={"qty": min_qty})
    assert r.status_code == 200
    assert r.json()["unit_price"] == tier_price
    assert r.json()["line_total"] == round(tier_price * min_qty, 2)


def test_price_endpoint_below_moq(client, all_products):
    p = next(p for p in all_products if p["moq"] > 1)
    assert client.get(f"/products/{p['id']}/price", params={"qty": p["moq"] - 1}).status_code == 422


def test_health_and_metrics(client):
    assert client.get("/health").json() == {"status": "ok"}
    client.get("/products/1")
    text = client.get("/metrics").text
    assert "http_requests_total" in text
    assert 'route="/products/{product_id}"' in text
    assert "http_request_duration_seconds_bucket" in text
