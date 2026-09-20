# Tier Architecture & Adaptive Stopping Policy

This document details the multi-tier optimization strategy, tried-ideas registry, noise-band plateau detection, and resource safety envelope governing autonomous execution in `ML_agent`.

---

## 1. Multi-Tier Optimization Architecture

The pipeline structures machine learning search into three progressive tiers. Rather than looping blindly within a single tier, the system advances to higher-leverage interventions as lower tiers converge.

```
       ┌───────────────────────────────┐
       │   Tier 1: Baseline Search     │
       │   (Model family exploration)  │
       └──────────────┬────────────────┘
                      │ Plateau / Max Diversity Reached
                      ▼
       ┌───────────────────────────────┐
       │  Tier 2: Feature Engineering  │
       │   (Transformations & Diffs)   │
       └──────────────┬────────────────┘
                      │ Feature Signal Stabilized
                      ▼
       ┌───────────────────────────────┐
       │  Tier 3: Tuning & Ensembling  │
       │  (Hyperparameters & Blends)   │
       └──────────────┬────────────────┘
                      │ Converged
                      ▼
       ┌───────────────────────────────┐
       │   Reporter: Final Synthesis   │
       └───────────────────────────────┘
```

### Tier 1: Baseline Model Family Exploration
- **Scope:** Evaluates diverse architectural families on the clean baseline feature set:
  - Gradient Boosted Decision Trees (`LightGBM`, `XGBoost`, `CatBoost`)
  - Linear/Regularized Baselines (`LogisticRegression`, `RidgeClassifier`)
  - Random Forests & Extra Trees
- **Objective:** Establish an out-of-fold generalization baseline ($\text{CV}_{\text{base}}$) without premature hyperparameter overfitting.
- **Escalation Trigger:** Plateau detected across diverse model families, or repetitive error signatures encountered.

### Tier 2: Feature Engineering & Transformation
- **Scope:** Re-engineers the tabular representation based on EDA correlation and feature importance:
  - Numerical interaction terms ($X_i \times X_j$, ratios)
  - Polynomial expansions and log/power scaling for skewed distributions
  - Categorical frequency and target encoding with out-of-fold regularization
  - Domain-specific date/time component extraction
- **Safety Gate:** Any column drop or destructive imputation triggers the `requires_human_approval` gate unless running in autonomous unguided mode.
- **Escalation Trigger:** Incremental feature validation deltas fall within the cross-validation noise band.

### Tier 3: Hyperparameter Optimization & Ensembling
- **Scope:** Deep fine-tuning of the top-ranked candidate models:
  - Learning rate, tree depth, subsample ratio, and regularization shrinkage ($\alpha, \lambda$)
  - Out-of-fold probability blending and weighted rank averaging
- **Convergence:** Handed off to `Reporter` when cross-validation performance stabilizes.

---

## 2. Adaptive Stopping Policy

The adaptive stopping policy replaces hardcoded iteration loops with model-driven decisions managed by `agents.adaptive_controller.AdaptiveStoppingPolicy`.

### 2.1 Tried-Ideas Registry (`TriedIdeasRegistry`)
- **Mechanism:** Before proposing a model architecture, hyperparameter combination, or feature transformation, the agent queries the in-memory ideas registry.
- **Deduplication:** Uses normalized semantic hashing (`hashlib.sha256(f"{phase}:{tier}:{norm_idea}")`) to detect duplicate hypotheses.
- **Guarantee:** Never repeats a rejected idea or identical parameter configuration within the same run.

### 2.2 Error-Signature Deduplication (`ErrorSignatureDeduplicator`)
- **Mechanism:** Normalizes runtime exceptions by stripping transient memory addresses, file paths, line numbers, and timestamps to yield a deterministic signature:
  $$\text{Sig} = \text{ErrorType} + \text{MD5}(\text{NormalizedMessage})$$
- **Policy:** If an identical error signature occurs 2+ consecutive times:
  - Blind retry is prohibited.
  - The controller triggers immediate approach mutation or tier escalation.

### 2.3 Noise-Band Plateau Detection (`NoiseBandPlateauDetector`)
- **Mechanism:** Evaluates cross-validation gains over a rolling window of $N=3$ attempts:
  $$\Delta_{\text{window}} = \text{Score}_t - \text{Score}_{t-N}$$
- **Noise Band Estimation:** The threshold is set dynamically:
  $$\text{Threshold} = \max(\epsilon_{\text{noise}}, 0.75 \times \sigma_{\text{CV}})$$
  *(where $\epsilon_{\text{noise}} = 0.002$ default, and $\sigma_{\text{CV}}$ is the standard deviation across cross-validation folds).*
- **Decision:** If $\Delta_{\text{window}} \le \text{Threshold}$, a plateau is declared. The supervisor escalates to the next optimization tier rather than burning iterations chasing statistical noise.

---

## 3. Resource Safety Envelope

The `SafetyEnvelope` guarantees that runaway training or stalled LLM reasoning loops cannot consume unbounded compute or crash the host environment.

| Dimension | Default Limit | Warning Threshold (85%) | Action at 100% |
|-----------|---------------|-------------------------|----------------|
| **Wall-Clock Time** | 900 seconds (15 min) | 765 seconds | Graceful wind-down to `reporter` |
| **Token Consumption** | 350,000 tokens | 297,500 tokens | Graceful wind-down to `reporter` |
| **Estimated Cost** | $3.00 USD | $2.55 USD | Graceful wind-down to `reporter` |
| **Global Iterations** | 200 steps | 170 steps | Circuit-breaker to `human_approval` |

### Graceful Wind-Down Guarantee
When any resource limit reaches 100%, the pipeline does **NOT** throw an unhandled exception or abort. Instead, `adaptive_controller` intercepts execution, logs `safety_envelope_exhausted`, routes directly to the `Reporter` specialist, and packages the best candidate model code, weights, and metrics discovered up to that point.
