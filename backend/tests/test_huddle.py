"""The group-chat flow end to end: thesis -> card -> tapbacks -> "$50 each" -> armed -> hack -> fill -> close -> score."""
import datetime as dt
import os
import shutil

import pytest

os.environ.setdefault("ARENA_MODE", "sim")
os.environ["TICK_SECONDS"] = "0"
os.environ["ADMIN_TOKEN"] = "test-admin"

from fastapi.testclient import TestClient  # noqa: E402

from app import backtest as B  # noqa: E402
from app import db as dbmod  # noqa: E402
from app import hl  # noqa: E402
from app.config import get_settings  # noqa: E402

ADMIN = {"x-admin-token": "test-admin"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cache = tmp_path / "candles"
    cache.mkdir()
    shutil.copy(B.FileCandles.DIR / "XMR_1d.csv", cache / "XMR_1d.csv")
    monkeypatch.setattr(B.FileCandles, "DIR", cache)
    B._source = None
    get_settings.cache_clear()
    dbmod.reset_engine_for_tests()
    hl.set_exchange_for_tests(hl.SimExchange(get_settings(), seed=3))
    from app.main import app

    with TestClient(app) as c:
        yield c
    hl.set_exchange_for_tests(None)


def say(c, hid, sender, text="", **kw):
    r = c.post(f"/huddle/{hid}/messages", json={"sender": sender, "text": text, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def bot(c, hid):
    return [m for m in c.get(f"/huddle/{hid}").json()["messages"] if m["from_bot"]]


def make_legion(c, slug="hack-club"):
    r = c.post("/admin/orgs", headers=ADMIN, json={"name": "Hack Club", "slug": slug, "leader": "matthew", "mandate": "buy XMR on hacks",
                                                  "limits": {"allowed_markets": ["XMR", "BTC"], "max_leverage": 3, "drawdown_flatten_pct": 30}})
    assert r.status_code == 201, r.text


def test_thesis_to_result_in_a_web_huddle(client):
    make_legion(client)
    h = client.get("/huddle/web/hack-club").json()
    hid = h["id"]
    assert h["org_slug"] == "hack-club" and h["quorum"] == 2

    say(client, hid, "Matthew", "let's buy xmr every time a major company gets hacked")
    th = client.get(f"/huddle/{hid}").json()["theses"]
    assert len(th) == 1 and th[0]["kind"] == "rule" and th[0]["status"] == "proposed"
    assert th[0]["test"]["real"] and th[0]["test"]["events"]["events"] > 3  # real cached XMR candles, several hacks in window
    card = bot(client, hid)[-1]
    assert card["kind"] == "card" and card["text"].startswith("Thesis 1, from Matthew") and "/t/" in card["text"]
    assert "—" not in card["text"]

    # chit-chat is ignored
    n = len(bot(client, hid))
    say(client, hid, "Lee", "lol the bybit one was wild")
    assert len(bot(client, hid)) == n

    # Lee thumbs up the card: quorum of 2 reached, no stake yet, bot asks how much
    say(client, hid, "Lee", reaction="like", target_guid=card["guid"])
    assert "How much each" in bot(client, hid)[-1]["text"]
    # "$50 each" arms it: two backers, $100 in paper money, deposited into the legion and allocated to a rule agent
    say(client, hid, "Lee", "let's put in 50 dollars each")
    t = client.get(f"/huddle/{hid}").json()["theses"][0]
    assert t["status"] == "live" and t["pledged_usd"] == 100 and t["agent_id"]
    assert "Thesis 1 is live inside Hack Club" in bot(client, hid)[-1]["text"]
    org = client.get("/orgs/hack-club").json()
    assert org["total_deposited"] == 100 and {d["depositor"] for d in org["depositors_detail"]} == {"Matthew", "Lee"}

    # someone reports a hack in the chat: the rule buys XMR with the pot, through the sandbox
    say(client, hid, "Sam", "protoss hack: Example Exchange drained for $40M https://example.com/x")
    msg = bot(client, hid)[-1]["text"]
    assert msg.startswith("Thesis 1 fired. Example Exchange drained for $40M (https://example.com/x)") and "XMR" in msg
    t = client.get(f"/huddle/{hid}").json()["theses"][0]
    assert len(t["triggers"]) == 1 and not t["triggers"][0]["closed"]
    fills = [f for f in client.get("/feed?limit=20").json() if f["kind"] == "fill" and f.get("market") == "XMR"]
    assert fills, "the fill is public"

    # the same event does not fire twice; the hold ends and the result comes back with the score
    from app import huddle as HD
    from app.db import session

    ex = hl.get_exchange()
    with session() as db:
        assert HD.settle(db, ex) == 0
        assert HD.settle(db, ex, now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=8)) == 1
    last = bot(client, hid)[-1]["text"]
    assert last.startswith("Thesis 1 closed. XMR") and "Record: " in last
    say(client, hid, "Lee", "protoss score")
    assert bot(client, hid)[-1]["text"].startswith("Score, by whose idea it was:\nMatthew:")

    # link previews: the thesis page carries OG tags and a PNG card
    tid = t["id"]
    page = client.get(f"/t/{tid}").text
    assert 'property="og:title" content="Thesis 1 from Matthew' in page and f"/og/t/{tid}.png" in page and "#/huddle/hack-club" in page
    png = client.get(f"/og/t/{tid}.png")
    assert png.status_code == 200 and png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_text_approvals_custom_pledge_and_dislike(client):
    hid = client.get("/huddle/web/friends").json()["id"]
    say(client, hid, "Ana", "what if we bought BTC every time a major company got hacked and held 3 days")
    t = client.get(f"/huddle/{hid}").json()["theses"][0]
    card = bot(client, hid)[-1]
    say(client, hid, "Bo", reaction="dislike", target_guid=card["guid"])
    assert client.get(f"/huddle/{hid}").json()["theses"][0]["status"] == "proposed"
    say(client, hid, "Bo", "in for $80")  # custom amount, also counts as backing; quorum and a pledge arm it
    t = client.get(f"/huddle/{hid}").json()["theses"][0]
    assert t["status"] == "live" and t["pledged_usd"] == 80
    assert {b["who"]: b["pledge_usd"] for b in t["backers"] if b["approved"]} == {"Ana": None, "Bo": 80}
    # a late joiner adds to the same pot
    say(client, hid, "Cy", "in for 20")
    t = client.get(f"/huddle/{hid}").json()["theses"][0]
    assert t["pledged_usd"] == 100 and "Pot is $100" in bot(client, hid)[-1]["text"]
    assert client.get(f"/agents/{t['agent_id']}").json()["metrics"]["equity"] == pytest.approx(100, abs=0.01)


def test_sports_call_is_logged_and_scored(client):
    hid = client.get("/huddle/web/hoops").json()["id"]
    say(client, hid, "Lee", "I think the Knicks win game 3 now that Brunson is coming off the injured list")
    t = client.get(f"/huddle/{hid}").json()["theses"][0]
    assert t["kind"] == "call" and "No Hyperliquid market" in bot(client, hid)[-1]["text"]
    say(client, hid, "Matthew", "+1")
    assert client.get(f"/huddle/{hid}").json()["theses"][0]["status"] == "live"
    say(client, hid, "Matthew", "protoss hit 1")
    assert "Lee: 1 of 1 right" in bot(client, hid)[-1]["text"]


def test_imessage_huddle_needs_the_bridge_token_and_uses_the_outbox(client):
    assert client.post("/huddle", json={"chat_id": "iMessage;+;chat1"}).status_code == 403
    h = client.post("/huddle", headers=ADMIN, json={"chat_id": "iMessage;+;chat1", "title": "the boys"}).json()
    hid = h["id"]
    assert client.post(f"/huddle/{hid}/messages", json={"sender": "x", "text": "hi"}).status_code == 403
    r = client.post(f"/huddle/{hid}/messages", headers=ADMIN, json={"sender": "Lee", "text": "protoss help", "guid": "G1"})
    assert r.status_code == 201
    out = client.get(f"/huddle/{hid}/outbox", headers=ADMIN).json()
    assert len(out) == 1 and out[0]["text"].startswith("I turn a trade idea")
    # the bridge sends it, then sees its own row come back through chat.db: that attaches the guid, no new message
    client.post(f"/huddle/{hid}/delivered", headers=ADMIN, json={"ids": [out[0]["id"]]})
    r = client.post(f"/huddle/{hid}/messages", headers=ADMIN, json={"sender": "me", "text": out[0]["text"], "guid": "G2", "from_me": True}).json()
    assert r["stored"] is False
    assert client.get(f"/huddle/{hid}/outbox", headers=ADMIN).json() == []
    # retried rows are idempotent on guid
    assert client.post(f"/huddle/{hid}/messages", headers=ADMIN, json={"sender": "Lee", "text": "protoss help", "guid": "G1"}).json()["stored"] is False


def test_legion_invite_link_preview(client):
    make_legion(client, "semis")
    page = client.get("/l/semis?from=lee").text
    assert 'content="lee invited you to Hack Club"' in page and "/og/l/semis.png" in page and "#/p/semis?from=lee" in page
    assert client.get("/og/l/semis.png").content[:4] == b"\x89PNG"
    assert client.get("/h/hack-club").status_code == 200 and client.get("/og/h/hack-club.png").content[:4] == b"\x89PNG"


def test_feed_parser_and_poll(client, monkeypatch):
    from app import huddle as HD
    from app.db import session

    rss = """<rss><channel>
      <item><title>Exchange X hacked, $90M drained</title><link>https://n.example/1</link><pubDate>%s</pubDate></item>
      <item><title>Bitcoin ETF flows rise</title><link>https://n.example/2</link></item>
    </channel></rss>""" % dt.datetime.now(dt.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    items = HD.parse_feed(rss)
    assert [i["title"] for i in items] == ["Exchange X hacked, $90M drained", "Bitcoin ETF flows rise"]
    monkeypatch.setenv("HUDDLE_HACK_FEEDS", '["https://n.example/rss"]')
    get_settings.cache_clear()
    with session() as db:
        assert HD.poll_feeds(db, hl.get_exchange(), fetch=lambda url: rss) == 1
        assert HD.poll_feeds(db, hl.get_exchange(), fetch=lambda url: rss) == 0  # deduped


def test_dwarkesh_rule_fires_on_a_new_episode(client):
    from app import huddle as HD
    from app.db import session

    hid = client.get("/huddle/web/pod").json()["id"]
    say(client, hid, "Ana", "Dwarkesh is always right. Trade every new episode")
    t = client.get(f"/huddle/{hid}").json()["theses"][0]
    assert t["kind"] == "rule" and t["label"].startswith("Buy xyz:NVDA on each new Dwarkesh Podcast episode") and t["proposal"]["holdings"][0]["market"] == "xyz:NVDA"
    say(client, hid, "Bo", "in for $80")
    assert client.get(f"/huddle/{hid}").json()["theses"][0]["status"] == "live"
    assert "Waiting for the next Dwarkesh Podcast episode." in bot(client, hid)[-1]["text"]
    now = dt.datetime.now(dt.timezone.utc)
    rss = """<rss><channel>
      <item><title>Someone new on AI</title><link>https://pod.example/new</link><pubDate>%s</pubDate><enclosure url="x.mp3"/></item>
      <item><title>An old one</title><link>https://pod.example/old</link><pubDate>%s</pubDate><enclosure url="y.mp3"/></item>
    </channel></rss>""" % (now.strftime("%a, %d %b %Y %H:%M:%S +0000"), (now - dt.timedelta(days=30)).strftime("%a, %d %b %Y %H:%M:%S +0000"))
    with session() as db:
        assert HD.poll_podcasts(db, hl.get_exchange(), fetch=lambda url: rss) == 1  # the 30-day-old episode is not news
        assert HD.poll_podcasts(db, hl.get_exchange(), fetch=lambda url: rss) == 0  # each episode fires once
    msg = bot(client, hid)[-1]["text"]
    assert msg.startswith("Thesis 1 fired. New Dwarkesh Podcast episode: Someone new on AI") and "Bought" in msg and "xyz:NVDA" in msg
    # a hack does not fire a podcast rule
    say(client, hid, "Ana", "protoss hack: Example Exchange drained")
    assert len(client.get(f"/huddle/{hid}").json()["theses"][0]["triggers"]) == 1


def test_tick_endpoint_is_admin_only_and_settles(client):
    assert client.post("/huddle/tick").status_code == 403
    r = client.post("/huddle/tick", headers=ADMIN, json={})
    assert r.status_code == 200 and r.json()["settled"] == 0 and "feed_events" in r.json()


def test_events_list_names_each_hack_with_the_move_after_it(client):
    hid = client.get("/huddle/web/ev").json()["id"]
    say(client, hid, "Ana", "let's buy xmr every time a major company gets hacked")
    say(client, hid, "Ana", "can you show me what all of the events are")  # a plain ask, no command word
    text = bot(client, hid)[-1]["text"]
    assert text.startswith("Idea 1 was tested on ") and "hacks. XMR over the 1d after each" in text
    assert "2025-02-21" in text and "Bybit" in text and text.rstrip().endswith("after any day.")
    say(client, hid, "Bo", "protoss events 1")
    assert bot(client, hid)[-1]["text"] == text
    # an idea that only mentions hacks is still an idea, not an events request
    say(client, hid, "Bo", "what if I bought BTC on hacks and held 3 days")
    assert len(client.get(f"/huddle/{hid}").json()["theses"]) == 2
