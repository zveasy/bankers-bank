import datetime as _dt

from quantengine.bridge.quant_bridge import publish_cash_position


def test_publish_dry_run():
    payload = {"bank_id": "abc", "asof_ts": _dt.datetime(2025, 1, 1, tzinfo=_dt.timezone.utc).isoformat()}
    res = publish_cash_position(payload, dry_run=True)
    assert res == {"ok": True, "dry_run": True, "key": "abc|2025-01-01T00:00:00+00:00"}


def test_publish_real_with_fake_transport():
    sent: list[tuple[str, bytes, bytes]] = []

    def fake_transport(topic: str, key: bytes, value: bytes):
        sent.append((topic, key, value))

    payload = {"bank_id": "xyz", "asof_ts": "2025-01-02T00:00:00+00:00"}
    res = publish_cash_position(payload, dry_run=False, transport=fake_transport, topic="cash_positions")

    assert res["ok"] is True and res["dry_run"] is False
    assert sent  # one message sent
    topic, key, val = sent[0]
    assert topic == "cash_positions"
    assert key.decode() == "xyz|2025-01-02T00:00:00+00:00"
    assert b"xyz" in val
