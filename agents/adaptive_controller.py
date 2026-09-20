"""
Adaptive Tier Controller & Safety Envelope for ML_agent.

Replaces blind iteration loops with an intelligent, model-driven stopping policy:
  1. TriedIdeasRegistry: Tracks hypotheses, model families, hyperparameters, and feature sets.
     Prevents the pipeline from repeating rejected ideas.
  2. ErrorSignatureDeduplicator: Detects repeated error signatures. If the same failure
     occurs 2+ times consecutively, immediately forces approach mutation or tier escalation.
  3. NoiseBandPlateauDetector: Evaluates whether metric deltas over recent attempts fall within
     the cross-validation noise band (std dev of CV folds or epsilon), detecting genuine plateaus.
  4. SafetyEnvelope: Enforces resource boundaries (wall-clock time, tokens, estimated cost,
     iteration ceiling). When approaching bounds, cleanly winds down to best-model synthesis.
  5. AdaptiveStoppingPolicy: Unified decision engine called by Supervisor and Judge.
"""
import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Literal, Optional, Tuple

from utils.safe import to_float, safe_diff, safe_round, safe_json
from tools.tracer import compute_error_signature, record_event

logger = logging.getLogger("agents.adaptive_controller")

# ---------------------------------------------------------------------------
# Default Safety Envelope Thresholds (Configurable via Environment)
# ---------------------------------------------------------------------------
DEFAULT_MAX_WALL_TIME_S = int(os.environ.get("SAFETY_MAX_WALL_TIME_S", "900"))       # 15 minutes
DEFAULT_MAX_TOTAL_TOKENS = int(os.environ.get("SAFETY_MAX_TOKENS", "350000"))         # 350k tokens
DEFAULT_MAX_COST_USD = float(os.environ.get("SAFETY_MAX_COST_USD", "3.00"))           # $3.00
DEFAULT_MAX_ITERATIONS = int(os.environ.get("SAFETY_MAX_ITERATIONS", "200"))
DEFAULT_PLATEAU_WINDOW = int(os.environ.get("PLATEAU_WINDOW", "3"))
DEFAULT_NOISE_BAND_EPSILON = float(os.environ.get("PLATEAU_NOISE_EPSILON", "0.002"))


# ---------------------------------------------------------------------------
# 1. Tried-Ideas Registry
# ---------------------------------------------------------------------------
class TriedIdeasRegistry:
    """
    In-memory registry of all hypotheses, model architectures, and feature engineering
    ideas tested during a run. Prevents duplicate cycles.
    """
    def __init__(self):
        self._runs: Dict[str, List[Dict[str, Any]]] = {}

    def record_idea(
        self,
        run_id: str,
        phase: str,
        tier: int,
        idea_summary: str,
        details: Optional[Dict[str, Any]] = None,
        outcome: str = "evaluated",
    ):
        if run_id not in self._runs:
            self._runs[run_id] = []

        norm_idea = idea_summary.strip().lower()
        idea_hash = hashlib.sha256(f"{phase}:{tier}:{norm_idea}".encode("utf-8")).hexdigest()[:12]

        entry = {
            "idea_id": idea_hash,
            "phase": phase,
            "tier": tier,
            "summary": idea_summary,
            "details": details or {},
            "outcome": outcome,
            "timestamp": time.time(),
        }
        self._runs[run_id].append(entry)
        return entry

    def is_tried(self, run_id: str, phase: str, idea_summary: str) -> Tuple[bool, Optional[str]]:
        """Check if an idea or semantically identical approach has already been tested."""
        if run_id not in self._runs:
            return False, None

        norm_idea = idea_summary.strip().lower()
        for item in self._runs[run_id]:
            if item["phase"] == phase:
                existing_norm = item["summary"].strip().lower()
                # Exact or high substring overlap check
                if norm_idea == existing_norm or (len(norm_idea) > 20 and norm_idea in existing_norm):
                    reason = f"Identical idea already tested at tier {item['tier']} with outcome: {item['outcome']}"
                    try:
                        from tools.tracer import record_event
                        record_event(
                            run_id, "adaptive_controller", "duplicate_idea_rejected",
                            phase=phase,
                            reason=reason,
                            idea=idea_summary[:200],
                            matched_outcome=item["outcome"],
                            matched_tier=item["tier"],
                        )
                    except Exception:
                        pass
                    return True, reason

        return False, None

    def get_tried_summaries(self, run_id: str, phase: Optional[str] = None) -> List[str]:
        if run_id not in self._runs:
            return []
        items = self._runs[run_id]
        if phase:
            items = [it for it in items if it["phase"] == phase]
        return [it["summary"] for it in items]


# ---------------------------------------------------------------------------
# 2. Error-Signature Deduplicator
# ---------------------------------------------------------------------------
class ErrorSignatureDeduplicator:
    """
    Tracks error signatures across attempts. Detects when the model or coder
    is stuck in an error loop (same error 2+ times consecutively).
    """
    def __init__(self):
        self._run_errors: Dict[str, List[str]] = {}

    def record_error(self, run_id: str, error_type: str, error_message: str) -> Tuple[str, bool]:
        """
        Records an error and returns (signature, is_consecutive_repeat).
        """
        sig = compute_error_signature(error_type, error_message)
        if run_id not in self._run_errors:
            self._run_errors[run_id] = []

        history = self._run_errors[run_id]
        is_repeat = (len(history) > 0 and history[-1] == sig)
        history.append(sig)
        return sig, is_repeat

    def should_force_escalate(self, run_id: str, max_consecutive: int = 2) -> bool:
        """True if the last `max_consecutive` errors have identical signature."""
        history = self._run_errors.get(run_id, [])
        if len(history) < max_consecutive:
            return False
        tail = history[-max_consecutive:]
        return len(set(tail)) == 1


# ---------------------------------------------------------------------------
# 3. Noise-Band Plateau Detector
# ---------------------------------------------------------------------------
class NoiseBandPlateauDetector:
    """
    Evaluates whether metric progression over the last N attempts is within
    the cross-validation noise band, signaling that further retries at this tier
    will produce diminishing returns.
    """
    def __init__(
        self,
        window: int = DEFAULT_PLATEAU_WINDOW,
        noise_epsilon: float = DEFAULT_NOISE_BAND_EPSILON,
    ):
        self.window = window
        self.noise_epsilon = noise_epsilon

    def check_plateau(
        self,
        metric_history: List[Any],
        cv_std: Optional[float] = None,
        higher_is_better: bool = True,
    ) -> Tuple[bool, str]:
        """
        Returns (is_plateau, explanation).
        """
        valid_scores = [to_float(m) for m in metric_history if to_float(m) is not None]
        if len(valid_scores) < self.window + 1:
            return False, "Insufficient history for plateau detection"

        recent_window = valid_scores[-self.window:]
        prior_score = valid_scores[-(self.window + 1)]

        # Determine noise band threshold (use CV std dev if available, else epsilon)
        threshold = max(self.noise_epsilon, cv_std * 0.75 if (cv_std is not None and cv_std > 0) else self.noise_epsilon)

        deltas = [safe_diff(recent_window[i], recent_window[i-1], higher_is_better) for i in range(1, len(recent_window))]
        total_gain = safe_diff(recent_window[-1], prior_score, higher_is_better)

        # Check if total gain across window is smaller than noise threshold
        if total_gain <= threshold:
            return True, f"Plateau detected: gain across last {self.window} attempts ({total_gain:+.4f}) is within CV noise band ({threshold:.4f})"

        # Check for oscillating/stagnant scores
        if all(abs(d) < threshold for d in deltas):
            return True, f"Plateau detected: all recent score deltas are below noise threshold ({threshold:.4f})"

        return False, f"Progressing normally (recent gain: {total_gain:+.4f})"


# ---------------------------------------------------------------------------
# 4. Resource Safety Envelope
# ---------------------------------------------------------------------------
class SafetyEnvelope:
    """
    Guarantees the system operates within defined resource boundaries.
    Winds down cleanly rather than crashing mid-loop when limits approach.
    """
    def __init__(
        self,
        max_wall_time_s: int = DEFAULT_MAX_WALL_TIME_S,
        max_tokens: int = DEFAULT_MAX_TOTAL_TOKENS,
        max_cost_usd: float = DEFAULT_MAX_COST_USD,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ):
        self.max_wall_time_s = max_wall_time_s
        self.max_tokens = max_tokens
        self.max_cost_usd = max_cost_usd
        self.max_iterations = max_iterations
        self._start_times: Dict[str, float] = {}

    def start_run(self, run_id: str):
        self._start_times[run_id] = time.time()

    def check_envelope(
        self,
        run_id: str,
        current_iteration: int,
        total_tokens: int = 0,
        estimated_cost: float = 0.0,
    ) -> Tuple[Literal["safe", "warn", "exhausted"], str]:
        """
        Check current resource consumption against envelope boundaries.
        """
        start = self._start_times.get(run_id, time.time())
        elapsed_s = time.time() - start

        # 1. Hard limits check (100% threshold)
        if elapsed_s >= self.max_wall_time_s:
            return "exhausted", f"Wall-clock safety limit reached ({elapsed_s:.0f}s >= {self.max_wall_time_s}s)"
        if total_tokens >= self.max_tokens:
            return "exhausted", f"Token safety limit reached ({total_tokens} >= {self.max_tokens})"
        if estimated_cost >= self.max_cost_usd:
            return "exhausted", f"Cost safety limit reached (${estimated_cost:.2f} >= ${self.max_cost_usd:.2f})"
        if current_iteration >= self.max_iterations:
            return "exhausted", f"Global iteration ceiling reached ({current_iteration} >= {self.max_iterations})"

        # 2. Warning check (85% threshold)
        if (
            elapsed_s >= self.max_wall_time_s * 0.85
            or total_tokens >= self.max_tokens * 0.85
            or estimated_cost >= self.max_cost_usd * 0.85
            or current_iteration >= self.max_iterations * 0.85
        ):
            return "warn", "Approaching safety envelope boundaries (85%+ capacity)"

        return "safe", "Within safety envelope"


# ---------------------------------------------------------------------------
# 5. Adaptive Stopping Policy (Master Controller)
# ---------------------------------------------------------------------------
class AdaptiveStoppingPolicy:
    """
    Coordinates registry, error deduplication, plateau detection, and safety envelope.
    Provides authoritative routing recommendations replacing hardcoded retry loops.
    """
    def __init__(self):
        self.ideas_registry = TriedIdeasRegistry()
        self.error_dedup = ErrorSignatureDeduplicator()
        self.plateau_detector = NoiseBandPlateauDetector()
        self.safety_envelope = SafetyEnvelope()

    def evaluate_next_action(
        self,
        run_id: str,
        state: Dict[str, Any],
        proposed_tier: int = 1,
        proposed_next_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates the current run state and returns the optimal adaptive action:
        - "continue": proceed with the proposed action
        - "escalate": advance tier (e.g. Tier 1 -> Tier 2 -> Tier 3)
        - "wind_down": safely wrap up and route to reporter node
        - "human_approval": prompt human with structured options
        """
        iteration = state.get("iteration", 0)
        metric_history = state.get("metric_history") or []
        retry_counts = state.get("retry_counts") or {}

        # 1. Check Safety Envelope
        tokens = state.get("total_tokens", 0)
        cost = state.get("total_cost_usd", 0.0)
        env_status, env_msg = self.safety_envelope.check_envelope(run_id, iteration, tokens, cost)

        if env_status == "exhausted":
            record_event(
                run_id=run_id,
                agent="adaptive_controller",
                event_type="safety_envelope_exhausted",
                reason=env_msg,
                decision="wind_down",
                next_agent="reporter",
            )
            return {
                "action": "wind_down",
                "next_agent": "reporter",
                "stop_reason": "safety_envelope_exhausted",
                "reason": env_msg,
            }

        # 2. Check Consecutive Error Loop
        if self.error_dedup.should_force_escalate(run_id):
            record_event(
                run_id=run_id,
                agent="adaptive_controller",
                event_type="error_loop_detected",
                reason="Consecutive identical error signatures detected",
                decision="escalate",
            )
            return {
                "action": "escalate",
                "next_agent": "features" if proposed_tier == 1 else "reporter",
                "tier": proposed_tier + 1,
                "reason": "Repeated identical error signature detected; mutating pipeline approach.",
            }

        # 3. Check Metric Plateau
        is_plateau, plateau_msg = self.plateau_detector.check_plateau(metric_history)
        if is_plateau:
            record_event(
                run_id=run_id,
                agent="adaptive_controller",
                event_type="plateau_detected",
                reason=plateau_msg,
                decision="escalate" if proposed_tier < 3 else "wind_down",
            )
            if proposed_tier == 1:
                return {
                    "action": "escalate",
                    "next_agent": "features",
                    "tier": 2,
                    "reason": f"{plateau_msg}. Advancing from Tier 1 (Baseline Models) to Tier 2 (Feature Engineering).",
                }
            elif proposed_tier == 2:
                return {
                    "action": "escalate",
                    "next_agent": "modeler",
                    "tier": 3,
                    "reason": f"{plateau_msg}. Advancing from Tier 2 to Tier 3 (Hyperparameter Optimization & Ensembling).",
                }
            else:
                return {
                    "action": "wind_down",
                    "next_agent": "reporter",
                    "stop_reason": "converged",
                    "reason": f"{plateau_msg}. All optimization tiers completed.",
                }

        # 4. Safe to continue with model-driven guidance
        return {
            "action": "continue",
            "next_agent": proposed_next_agent or "modeler",
            "tier": proposed_tier,
            "reason": "Normal progress within safety envelope.",
        }


# Global singleton controller
adaptive_controller = AdaptiveStoppingPolicy()
