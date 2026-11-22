DEMO_QUERIES = (
    ("窗边人像", "window-light-portrait"),
    ("西餐厅", "window-light-portrait"),
    ("火车窗边", "window-light-portrait"),
    ("高铁窗边", "window-light-portrait"),
    ("黄山", "sea-of-clouds-sunrise"),
    ("光明顶", "sea-of-clouds-sunrise"),
    ("黄山云海", "sea-of-clouds-sunrise"),
)


async def test_demo_search_terms_hit_topics_before_works(client):
    for query, slug in DEMO_QUERIES:
        payload = (await client.get("/api/v1/search", params={"q": query})).json()
        assert payload["topics"], query
        assert payload["topics"][0]["slug"] == slug
        assert payload["items"][0]["kind"] == "topic"
        page = await client.get("/search", params={"q": query})
        assert page.status_code == 200
        assert payload["topics"][0]["name"] in page.text
        topic_at = page.text.find("题材")
        work_at = page.text.find("成片")
        assert topic_at != -1 and work_at != -1 and topic_at < work_at


async def test_channel_pages_list_their_own_topics(client):
    portrait = await client.get("/portrait")
    assert portrait.status_code == 200
    assert "窗边人像" in portrait.text
    assert "黄山" not in portrait.text
    landscape = await client.get("/landscape")
    assert landscape.status_code == 200
    assert "黄山" in landscape.text
    assert "窗边人像" not in landscape.text
