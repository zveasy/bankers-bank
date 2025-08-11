import datetime as _dt

import pytest

from quantengine.liquidity.policy import (
    LiquidityPolicy,
    compute_buffer,
    evaluate,
    is_holiday,
)


@pytest.mark.parametrize(
    "available, min_bps, expected",
    [
        (1_000_000, 500, 50_000),
        (0, 500, 0),
        (123_456.78, 250, round(123_456.78 * 0.025, 2)),
    ],
)
def test_compute_buffer(available, min_bps, expected):
    assert compute_buffer(available, min_bps) == expected


def test_is_holiday():
    cal = {"2025-12-25"}
    assert is_holiday(_dt.date(2025, 12, 25), cal) is True
    assert is_holiday(_dt.date(2025, 12, 24), cal) is False


@pytest.mark.parametrize(
    "policy_kwargs,available,draw,asof,reasons,allowed",
    [
        # Happy path – ok
        ({"min_cash_bps": 500, "max_draw_bps": 10_000}, 1_000_000, 100_000, _dt.date(2025, 1, 15), [], 100_000),
        # Buffer violation
        ({"min_cash_bps": 500}, 1_000_000, 970_000, _dt.date(2025, 1, 15), ["min_buffer"], 0),
        # Max draw cap violation
        ({"max_draw_bps": 1000}, 1_000_000, 200_000, _dt.date(2025, 1, 15), ["max_draw_cap"], 0),
        # Holiday violation
        ({"settlement_calendar": {"2025-12-25"}}, 1_000_000, 100_000, _dt.date(2025, 12, 25), ["holiday"], 0),
        # Combined reasons
        ({"min_cash_bps": 500, "max_draw_bps": 1000, "settlement_calendar": {"2025-12-25"}}, 1_000_000, 200_000, _dt.date(2025, 12, 25), ["holiday", "max_draw_cap"], 0),
    ],
)
def test_evaluate(policy_kwargs, available, draw, asof, reasons, allowed):
    policy = LiquidityPolicy(**policy_kwargs)
    res = evaluate(policy, available_cash_usd=available, requested_draw_usd=draw, asof=asof)
    assert set(res["reasons"]) == set(reasons)
    assert res["allowed_draw_usd"] == allowed
    assert res["ok"] == (reasons == [])
