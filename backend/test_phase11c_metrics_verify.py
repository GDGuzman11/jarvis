"""Phase 11C verification — MetricsEvent + _compute_cost.

Targeted checks for the cost/latency metrics added by the backend-agent:

* :func:`backend.ai.claude_client._compute_cost` — pure price-card math.
* :class:`backend.events.MetricsEvent` — dataclass shape, ``type`` discriminator,
  dict serialisation, and membership in the ``EventType`` literal.

All pure / in-memory: no API key, no network, no audio device.
"""

from __future__ import annotations

import math
import typing

from backend.ai.claude_client import (
    PRICE_CACHE_READ_PER_MTOK,
    PRICE_CACHE_WRITE_PER_MTOK,
    PRICE_INPUT_PER_MTOK,
    PRICE_OUTPUT_PER_MTOK,
    _compute_cost,
)
from backend.events import EventType, MetricsEvent


# --- Price constants ---------------------------------------------------------


def test_price_constants_match_opus_4_7_card() -> None:
    assert PRICE_INPUT_PER_MTOK == 15.00
    assert PRICE_OUTPUT_PER_MTOK == 75.00
    assert PRICE_CACHE_WRITE_PER_MTOK == 3.75
    assert PRICE_CACHE_READ_PER_MTOK == 1.50


# --- _compute_cost -----------------------------------------------------------
# Signature: _compute_cost(input, output, cache_write, cache_read)


def test_compute_cost_input_output_only() -> None:
    # 1000 input tokens @ $15/M = 1000/1_000_000 * 15 = 0.015
    # 1000 output tokens @ $75/M = 1000/1_000_000 * 75 = 0.075
    # total = 0.09  (the task brief's "$0.00009" is a 1000x typo; its own
    # inline arithmetic "1000/1M * $15 + 1000/1M * $75" equals 0.09)
    cost = _compute_cost(1000, 1000, 0, 0)
    assert math.isclose(cost, 0.09, rel_tol=1e-9, abs_tol=1e-12)


def test_compute_cost_cache_only_path() -> None:
    # cache_write=1000 @ $3.75/M = 1000/1_000_000 * 3.75 = 0.00375
    # cache_read=1000  @ $1.50/M = 1000/1_000_000 * 1.50 = 0.0015
    # total = 0.00525
    cost = _compute_cost(0, 0, 1000, 1000)
    assert math.isclose(cost, 0.00525, rel_tol=1e-9, abs_tol=1e-12)


def test_compute_cost_one_million_each_is_exactly_90() -> None:
    # 1M input @ $15 + 1M output @ $75 = $90.00 exactly
    cost = _compute_cost(1_000_000, 1_000_000, 0, 0)
    assert math.isclose(cost, 90.00, rel_tol=1e-9, abs_tol=1e-9)


def test_compute_cost_all_four_buckets() -> None:
    # 1M of each bucket: 15 + 75 + 3.75 + 1.50 = 95.25
    cost = _compute_cost(1_000_000, 1_000_000, 1_000_000, 1_000_000)
    assert math.isclose(cost, 95.25, rel_tol=1e-9, abs_tol=1e-9)


def test_compute_cost_zero_is_zero() -> None:
    assert _compute_cost(0, 0, 0, 0) == 0.0


# --- MetricsEvent shape ------------------------------------------------------


def test_metrics_event_type_field_is_metrics() -> None:
    evt = MetricsEvent(
        cost_usd=0.00009,
        latency_ms=1234,
        model="claude-opus-4-7",
        input_tokens=1000,
        output_tokens=1000,
    )
    assert evt.type == "metrics"


def test_metrics_event_serialises_with_all_keys() -> None:
    evt = MetricsEvent(
        cost_usd=0.00009,
        latency_ms=1234,
        model="claude-opus-4-7",
        input_tokens=1000,
        output_tokens=1000,
        cache_read_tokens=50,
        cache_write_tokens=20,
    )
    d = evt.to_dict()
    expected_keys = {
        "cost_usd",
        "latency_ms",
        "model",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "type",
        "timestamp",
    }
    assert set(d.keys()) == expected_keys
    assert d["type"] == "metrics"
    assert d["cost_usd"] == 0.00009
    assert d["latency_ms"] == 1234
    assert d["model"] == "claude-opus-4-7"
    assert d["input_tokens"] == 1000
    assert d["output_tokens"] == 1000
    assert d["cache_read_tokens"] == 50
    assert d["cache_write_tokens"] == 20
    assert isinstance(d["timestamp"], str) and d["timestamp"]


def test_metrics_event_cache_fields_default_to_zero() -> None:
    evt = MetricsEvent(
        cost_usd=0.0,
        latency_ms=0,
        model="claude-opus-4-7",
        input_tokens=0,
        output_tokens=0,
    )
    assert evt.cache_read_tokens == 0
    assert evt.cache_write_tokens == 0


def test_metrics_in_event_type_literal() -> None:
    assert "metrics" in typing.get_args(EventType)


def test_metrics_event_to_json_is_valid_json() -> None:
    import json

    evt = MetricsEvent(
        cost_usd=90.0,
        latency_ms=500,
        model="claude-opus-4-7",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    parsed = json.loads(evt.to_json())
    assert parsed["type"] == "metrics"
    assert parsed["cost_usd"] == 90.0
