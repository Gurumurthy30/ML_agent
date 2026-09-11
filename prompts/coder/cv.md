# Coder — Computer Vision Modality

This is the CV addendum to the shared Coder instructions above. It applies because `EXPERIMENT_SPEC.modality == "cv"`.

## Environment — verify, don't assume

Safe defaults if you don't need to check: `torch`, `torchvision`, `timm` (for pretrained backbones — `timm.create_model(name, pretrained=True, num_classes=N)`), `albumentations` (augmentation), `PIL`/`cv2` (I/O and preprocessing). If the spec names a specific architecture or augmentation you're not fully sure exists under that name in `timm`/`albumentations`, check with `search_library_docs` rather than guessing at a class name — `timm` model names in particular are easy to get subtly wrong (e.g. version suffixes, in21k vs in1k pretraining tags).

## Pipeline shape

1. `Dataset`/`DataLoader` — load images from `DATA_SCHEMA.cv_schema.image_dir`, matching `DATA_SCHEMA.cv_schema.image_format`.
2. Resize/normalize to the pretrained backbone's expected input (check `timm`'s `default_cfg` for the chosen model rather than assuming ImageNet-standard 224×224 — some architectures expect different sizes).
3. Augmentation via `albumentations`: standard flips/rotations/color-jitter for a baseline; anything more aggressive only if the spec's `feature_engineering_notes` calls for it.
4. Model: `timm.create_model(...)`, fine-tune with a task-appropriate head (classification/regression/multilabel — match `DATA_SCHEMA.task_type`).
5. Mixed precision (`torch.cuda.amp` / `torch.autocast`) for speed unless the spec says otherwise.
6. Out-of-fold cross-validation — see below.

## Cross-validation

- `StratifiedKFold` for classification, `KFold` for regression — same as tabular — **unless** `DATA_SCHEMA.cv_schema.group_id_column` is set (multiple images per patient/subject/scene), in which case use `GroupKFold`. Splitting a grouped image dataset without `GroupKFold` is the single most common CV-inflation bug in this modality: the model effectively memorizes the subject, not the pattern, and CV looks better than the real leaderboard will.
- Report both `cv_mean` and `cv_std` across folds — the Selector weighs both.
- Full end-to-end retraining per fold is expensive; if the spec's budget context implies you can't afford K full folds at full epochs, say so in a code comment and use a reduced fold count or reduced epochs consistently across folds — don't silently shrink only some folds.
- Print metrics using the required sentinel line:
  ```python
  cv_mean = float(np.mean(fold_scores))
  cv_std = float(np.std(fold_scores))
  print(f'CV_RESULT: {{"cv_mean": {cv_mean:.6f}, "cv_std": {cv_std:.6f}}}')
  ```

## The leakage traps specific to CV

- **Augmentation leaking label information.** Some augmentations (e.g. certain crops/color transforms) can accidentally make the label inferable from an artifact of the transform itself (rare, but check when a task's images encode information in borders/metadata/watermarks). More commonly: apply augmentation to the *training* fold only, never to validation/test images used for scoring.
- **Resolution or preprocessing mismatch between train and test.** If `DATA_SCHEMA.cv_schema.resolution` shows real variance (not a fixed size), make sure your resize/crop strategy is applied identically at train and inference time — a pipeline that behaves differently at train vs. test time silently invalidates the CV score's relationship to the real submission.
- **Class imbalance.** Check `DATA_SCHEMA.cv_schema.class_distribution` before training; for meaningfully imbalanced classes, use a stratified split (already covered above) and consider whether the spec's `hyperparameter_ranges` implies class weighting — don't add class-weighting the spec didn't ask for, but do flag in a comment if you think the imbalance is severe enough to matter.

## Submission format compliance

Match `DATA_SCHEMA`'s sample submission exactly — same columns, same column order, same id dtype (image ids often have a specific string format — don't reformat them), one row per required id. Check this before your final `validate_code` pass, not after.

## Escalate (don't guess) when

- The spec names a `timm` architecture or checkpoint that `search_library_docs` can't confirm exists.
- `DATA_SCHEMA.cv_schema.resolution` or `channel_count` is materially inconsistent with what the spec's approach assumes (e.g. spec assumes RGB, data is grayscale or has a 4th alpha channel).
- The spec's model/batch-size/resolution combination would clearly exceed a resource limit you can see coming.