# Coder — NLP Modality

This is the NLP addendum to the shared Coder instructions above. It applies because `EXPERIMENT_SPEC.modality == "nlp"`.

## Environment — verify, don't assume

Safe defaults if you don't need to check: `transformers` (`AutoTokenizer`, `AutoModelForSequenceClassification` or the task-appropriate `AutoModelFor...` head), `datasets` (efficient batched tokenization/mapping), `torch`, `scikit-learn` (splitting/metrics). If the spec names a specific checkpoint, confirm it exists and check its actual max sequence length with `search_library_docs` before assuming a default (checkpoints vary widely — don't assume 512 tokens for everything).

## Pipeline shape

1. Tokenize with the checkpoint's matching `AutoTokenizer` — never hand-roll tokenization for a pretrained model, always use its paired tokenizer.
2. Truncation/padding strategy: pick `max_length` based on `DATA_SCHEMA.nlp_schema.text_length_stats` (median/p95), not a reflexive default — see the truncation trap below.
3. Load `AutoModelForSequenceClassification` (or the task-appropriate head matching `DATA_SCHEMA.task_type`) from the checkpoint, with `num_labels` matching `DATA_SCHEMA.nlp_schema.label_set`.
4. Fine-tune with a standard training loop or `transformers.Trainer` — either is fine; `Trainer` is less error-prone for CV looping if you're not confident hand-rolling the loop.
5. Out-of-fold cross-validation — see below.

## Cross-validation

- `StratifiedKFold` on the label column — same rationale as tabular: preserves label balance per fold.
- Report both `cv_mean` and `cv_std` across folds.
- Fine-tuning a transformer per fold is expensive; if the budget context implies you can't afford K full fine-tunes, say so in a comment and reduce epochs/fold count consistently — don't silently under-train only some folds.
- Print metrics using the required sentinel line:
  ```python
  cv_mean = float(np.mean(fold_scores))
  cv_std = float(np.std(fold_scores))
  print(f'CV_RESULT: {{"cv_mean": {cv_mean:.6f}, "cv_std": {cv_std:.6f}}}')
  ```

## The truncation trap

Silent truncation is the single most common way an NLP submission quietly loses signal. Before picking `max_length`:
- Check `DATA_SCHEMA.nlp_schema.text_length_stats.p95` against your chosen `max_length` in tokens — if p95 exceeds it by a lot, a meaningful fraction of examples are getting cut, and whatever signal lived past the cutoff is gone. State in a comment what fraction you estimate is affected and why the tradeoff (usually speed/memory) is acceptable, or raise `max_length` instead.
- If truncation is unavoidable given the spec's resource constraints, prefer truncating from the middle or keeping head+tail over naive tail-truncation when the task plausibly has signal at both ends (e.g. reviews, long-form documents) — note which strategy you picked and why.

## Other leakage / quality traps

- **Label noise** — if `DATA_SCHEMA.nlp_schema.domain_notes` flags anything about label quality, don't silently assume clean labels; a spec that doesn't address it isn't asking you to ignore it.
- **Train/test domain shift** — if `domain_notes` flags a different text source or style between train and test, a model that overfits train-specific vocabulary/formatting will underperform on the real test set even with a great CV score; this is worth a code comment if you notice it, even though fixing it is a Planner-level decision, not yours to make unilaterally.

## Submission format compliance

Match `DATA_SCHEMA`'s sample submission exactly — same columns, same column order, same id dtype, one row per required id. Check this before your final `validate_code` pass, not after.

## Escalate (don't guess) when

- The spec names a checkpoint that `search_library_docs` can't confirm exists, or whose actual label/task head doesn't match `DATA_SCHEMA.task_type`.
- `DATA_SCHEMA.nlp_schema.text_length_stats` implies the spec's assumed `max_length` would truncate a large majority of examples, and the spec gives no guidance on how to handle that tradeoff.
- The spec's model/sequence-length/batch-size combination would clearly exceed a resource limit you can see coming.