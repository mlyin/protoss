"""scripts/imessage_bridge.py against a chat.db built with the same tables Messages.app uses."""
import importlib.util
import sqlite3
from pathlib import Path

spec = importlib.util.spec_from_file_location("bridge", Path(__file__).resolve().parents[2] / "scripts" / "imessage_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def typedstream(text: str) -> bytes:
    raw = text.encode()
    n = bytes([len(raw)]) if len(raw) < 0x80 else b"\x81" + len(raw).to_bytes(2, "little")
    return b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + n + raw + b"\x86\x84\x02iI"


def make_db(path):
    db = sqlite3.connect(path)
    db.executescript("""
      CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
      CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, guid TEXT, display_name TEXT);
      CREATE TABLE chat_handle_join (chat_id INTEGER, handle_id INTEGER);
      CREATE TABLE message (ROWID INTEGER PRIMARY KEY, guid TEXT, text TEXT, attributedBody BLOB, is_from_me INTEGER, handle_id INTEGER,
                            associated_message_type INTEGER, associated_message_guid TEXT, date INTEGER);
      CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
      INSERT INTO handle VALUES (1, '+15551230001'), (2, 'sam@example.com');
      INSERT INTO chat VALUES (7, 'iMessage;+;chat777', 'the boys'), (8, 'iMessage;-;+15551230001', NULL);
      INSERT INTO chat_handle_join VALUES (7, 1), (7, 2), (8, 1);
    """)
    rows = [
        (1, "G1", "let's buy xmr every time a major company gets hacked", None, 1, 0, 0, None, 783_000_000_000_000_000),
        (2, "G2", None, typedstream("Thesis 1, from me\nBuy XMR on major hacks, hold 7d " + "x" * 200), 1, 0, 0, None, 783_000_001_000_000_000),
        (3, "G3", "Liked “Thesis 1…”", None, 0, 1, 2001, "p:0/G2", 783_000_002_000_000_000),
        (4, "G4", "$50 each", None, 0, 2, 0, None, 783_000_003_000_000_000),
        (5, "G5", "Removed a like", None, 0, 1, 3001, "bp:G2", 783_000_004_000_000_000),
    ]
    db.executemany("INSERT INTO message VALUES (?,?,?,?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO chat_message_join VALUES (7, ?)", [(r[0],) for r in rows])
    db.commit()
    return db


def test_decode_and_mapping():
    assert bridge.decode_attributed_body(typedstream("in for 80")) == "in for 80"
    long = "y" * 300
    assert bridge.decode_attributed_body(typedstream(long)) == long
    assert bridge.decode_attributed_body(b"nothing here") is None
    assert bridge.reaction_of(2001) == "like" and bridge.reaction_of(3001) == "-like" and bridge.reaction_of(0) is None
    assert bridge.target_of("p:0/ABC-123") == "ABC-123" and bridge.target_of("bp:ABC-123") == "ABC-123"
    assert bridge.name_for("+15551230001", {"+15551230001": "Lee"}, "Matthew", False) == "Lee"
    assert bridge.name_for("+15559998888", {}, "Matthew", False) == "…8888"
    assert bridge.name_for("", {}, "Matthew", True) == "Matthew"


def test_reads_chat_db(tmp_path):
    p = tmp_path / "chat.db"
    make_db(p).close()
    db = bridge.connect(p)
    chats = bridge.list_chats(db)
    assert chats[0]["guid"] == "iMessage;+;chat777" and chats[0]["name"] == "the boys" and "sam@example.com" in chats[0]["members"]
    rows = bridge.new_rows(db, bridge.chat_rowid(db, "iMessage;+;chat777"), 0)
    assert [r["guid"] for r in rows] == ["G1", "G2", "G3", "G4", "G5"]
    assert rows[1]["text"].startswith("Thesis 1, from me") and rows[1]["from_me"]
    assert rows[2]["reaction"] == "like" and rows[2]["target"] == "G2" and rows[2]["handle"] == "+15551230001"
    assert rows[4]["reaction"] == "-like"
    assert abs(rows[0]["ts"] - (783_000_000 + bridge.APPLE_EPOCH)) < 1
    assert len(bridge.new_rows(db, 7, 3)) == 2
