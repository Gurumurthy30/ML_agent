"""
Unit tests for agents.adaptive_controller:
  - TriedIdeasRegistry
  - ErrorSignatureDeduplicator
  - NoiseBandPlateauDetector
  - SafetyEnvelope
  - AdaptiveStoppingPolicy
"""
import time
import pytest

from agents.adaptive_controller import (
    TriedIdeasRegistry,
    ErrorSignatureDeduplicator,
    NoiseBandPlateauDetector,
    SafetyEnvelope,
    AdaptiveStoppingPolicy,
)

def test_tried_ideas_registry():
    reg = TriedIdeasRegistry()
    run_id = "test_run_1"

    # Record first idea
    entry = reg.record_idea(run_id, "modeler", 1, "LightGBM with max_depth=6")
    assert entry["phase"] == "modeler"
    assert entry["tier"] == 1

    # Check identical idea
    is_tried, reason = reg.is_tried(run_id, "modeler", "LightGBM with max_depth=6")
    assert is_tried is True
    assert "already tested" in reason

    # Check new idea
    is_tried_new, _ = reg.is_tried(run_id, "modeler", "CatBoost with iterations=500")
    assert is_tried_new is False

    # Check summaries
    summaries = reg.get_tried_summaries(run_id, "modeler")
    assert len(summaries) == 1
    assert "LightGBM" in summaries[0]


def test_error_signature_deduplicator():
    dedup = ErrorSignatureDeduplicator()
    run_id = "test_run_err"

    # First error
    sig1, is_repeat1 = dedup.record_error(run_id, "ValueError", "could not convert string to float: 'abc'")
    assert is_repeat1 is False
    assert dedup.should_force_escalate(run_id) is False

    # Second consecutive identical error
    sig2, is_repeat2 = dedup.record_error(run_id, "ValueError", "could not convert string to float: 'xyz'")
    assert sig1 == sig2  # Normalized signature matches
    assert is_repeat2 is True
    assert dedup.should_force_escalate(run_id, max_consecutive=2) is True


def test_noise_band_plateau_detector():
    detector = NoiseBandPlateauDetector(window=3, noise_epsilon=0.005)

    # Insufficient history
    is_plat, _ = detector.check_plateau([0.75, 0.76])
    assert is_plat is False

    # Meaningful progression
    is_plat, _ = detector.check_plateau([0.70, 0.72, 0.75, 0.78])
    assert is_plat is False

    # Plateau (stagnant scores within epsilon)
    is_plat, reason = detector.check_plateau([0.800, 0.801, 0.8015, 0.802])
    assert is_plat is True
    assert "Plateau detected" in reason


def test_safety_envelope_limits():
    # Test iteration limit
    env = SafetyEnvelope(max_iterations=10, max_tokens=1000, max_cost_usd=1.0, max_wall_time_s=60)
    env.start_run("run_env")

    status, msg = env.check_envelope("run_env", current_iteration=5, total_tokens=100, estimated_cost=0.1)
    assert status == "safe"

    # Warn threshold (85%+)
    status_w, _ = env.check_envelope("run_env", current_iteration=9, total_tokens=100, estimated_cost=0.1)
    assert status_w == "warn"

    # Hard limit exhausted
    status_e, reason = env.check_envelope("run_env", current_iteration=10, total_tokens=100, estimated_cost=0.1)
    assert status_e == "exhausted"
    assert "Global iteration ceiling" in reason


def test_adaptive_stopping_policy_decisions():
    policy = AdaptiveStoppingPolicy()
    run_id = "test_policy_run"
    policy.safety_envelope.start_run(run_id)

    # 1. Normal state -> continue
    state = {
        "iteration": 2,
        "metric_history": [0.70, 0.75],
        "total_tokens": 5000,
        "total_cost_usd": 0.05,
    }
    rec = policy.evaluate_next_action(run_id, state, proposed_tier=1)
    assert rec["action"] == "continue"

    # 2. Plateau state -> escalate
    plateau_state = {
        "iteration": 5,
        "metric_history": [0.800, 0.801, 0.8015, 0.802],
        "total_tokens": 10000,
        "total_cost_usd": 0.10,
    }
    rec_p = policy.evaluate_next_action(run_id, plateau_state, proposed_tier=1)
    assert rec_p["action"] == "escalate"
    assert rec_p["tier"] == 2
    assert rec_p["next_agent"] == "features"
