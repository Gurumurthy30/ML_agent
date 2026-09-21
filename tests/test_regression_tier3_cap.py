import pytest
from agents.adaptive_controller import AdaptiveStoppingPolicy


def test_plateau_detector_caps_at_tier_2():
    policy = AdaptiveStoppingPolicy()
    run_id = "test_tier3_cap_run"

    # Provide metric history that triggers a plateau (window=3, small deltas)
    # E.g. [0.80, 0.8001, 0.8002, 0.80015]
    state = {
        "iteration": 10,
        "metric_history": [0.80, 0.8001, 0.8002, 0.80015],
        "retry_counts": {1: 1, 2: 1},
    }

    # At proposed_tier=1, it should escalate to tier 2
    rec_tier1 = policy.evaluate_next_action(run_id=run_id, state=state, proposed_tier=1)
    assert rec_tier1["action"] == "escalate"
    assert rec_tier1["tier"] == 2
    assert rec_tier1["next_agent"] == "features"

    # At proposed_tier=2, it MUST NOT propose tier 3; it should cap at tier 2 and wind down
    rec_tier2 = policy.evaluate_next_action(run_id=run_id, state=state, proposed_tier=2)
    assert rec_tier2["action"] == "wind_down"
    assert rec_tier2["next_agent"] == "reporter"
    assert rec_tier2.get("tier") is None or rec_tier2.get("tier") <= 2
    assert rec_tier2.get("tier") != 3


def test_error_dedup_caps_at_tier_2():
    policy = AdaptiveStoppingPolicy()
    run_id = "test_error_cap_run"

    # Record consecutive identical errors to trigger force escalate
    policy.error_dedup.record_error(run_id, "ValueError", "bad input shape")
    policy.error_dedup.record_error(run_id, "ValueError", "bad input shape")

    state = {"iteration": 5, "metric_history": []}

    # At proposed_tier=2, error loop must not propose tier 3
    rec = policy.evaluate_next_action(run_id=run_id, state=state, proposed_tier=2)
    assert rec.get("tier") != 3
    assert rec["action"] == "wind_down"
