"""
Centralized configuration for pipeline orchestration, loop limits, and convergence rules.
All values are configurable via environment variables with sensible, production-ready defaults.
"""
import os

# Global iteration ceiling — last-resort circuit breaker for the entire graph.
GLOBAL_ITER_CEILING: int = int(os.environ.get("PIPELINE_GLOBAL_ITER_CEILING", "200"))

# Per-agent exploration loop safety ceiling — replaces arbitrary 5-9 low caps.
# Generous floor/cap allowing improving models to converge without being cut off early.
LOOP_SAFETY_CEILING: int = int(os.environ.get("PIPELINE_LOOP_SAFETY_CEILING", "30"))

# Minimum metric delta required to consider an iteration or retry an actual improvement.
# Any delta smaller than this is treated as a stall / plateau.
METRIC_IMPROVEMENT_EPSILON: float = float(os.environ.get("PIPELINE_METRIC_EPSILON", "0.001"))

# Maximum number of automated retries permitted per tier before human intervention.
TIER1_RETRY_BUDGET: int = int(os.environ.get("PIPELINE_TIER1_BUDGET", "2"))
TIER2_RETRY_BUDGET: int = int(os.environ.get("PIPELINE_TIER2_BUDGET", "2"))

# Consecutive iterations without improvement before an exploration loop stops early on stall/plateau.
CONVERGENCE_PATIENCE: int = int(os.environ.get("PIPELINE_CONVERGENCE_PATIENCE", "3"))
