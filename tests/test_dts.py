"""Unit tests for the DTS formula and depth routing (Module 1)."""
import pytest

from app import dts_engine


def test_neutral_baseline_routes_standard():
    result = dts_engine.calculate_dts(0, 0, 0, 0, 0)
    assert result["dts"] == 70
    assert result["depth"] == "standard"


def test_high_trust_developer_routes_shallow():
    # perfect record: no bugs, no reverts, +15% coverage, perfect accept rate
    result = dts_engine.calculate_dts(0.0, 0.0, 15.0, 0, 1.0)
    assert result["dts"] >= 80
    assert result["depth"] == "shallow"


def test_low_trust_developer_routes_block():
    result = dts_engine.calculate_dts(2.4, 0.25, -6.0, 3, 0.2)
    assert result["dts"] == 0
    assert result["depth"] == "block"


def test_deep_band():
    result = dts_engine.calculate_dts(1.2, 0.10, -2.0, 1, 0.4)
    assert 20 <= result["dts"] <= 49
    assert result["depth"] == "deep"


def test_score_is_clamped_to_0_100():
    assert dts_engine.calculate_dts(10, 1, -100, 10, 0)["dts"] == 0
    assert dts_engine.calculate_dts(0, 0, 1000, 0, 1)["dts"] == 100


def test_breakdown_is_explainable_and_sums_to_raw_score():
    result = dts_engine.calculate_dts(0.5, 0.1, 5.0, 1, 0.8)
    breakdown = result["breakdown"]
    assert breakdown["baseline"] == 70
    raw = sum(breakdown.values())
    assert result["dts"] == max(0, min(100, round(raw)))
    # every input factor must appear in the breakdown — no black-box scoring
    for factor in ("bug_rate", "revert_rate", "coverage_delta",
                   "security_count", "accept_rate"):
        assert factor in breakdown


@pytest.mark.parametrize("dts,expected", [
    (100, "shallow"), (80, "shallow"),
    (79, "standard"), (50, "standard"),
    (49, "deep"), (20, "deep"),
    (19, "block"), (0, "block"),
])
def test_depth_boundaries(dts, expected):
    assert dts_engine.get_review_depth(dts) == expected


def test_unknown_developer_gets_neutral_default(tmp_path, monkeypatch):
    from app import config, database
    monkeypatch.setattr(config, "DATABASE_PATH", str(tmp_path / "t.db"))
    database.init_db()
    trust = dts_engine.get_or_default_dts("brand-new-dev")
    assert trust["dts"] == 70
    assert trust["depth"] == "standard"
