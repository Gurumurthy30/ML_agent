# Coder — Audio Modality

This is the audio addendum to the shared Coder instructions above. It applies because `EXPERIMENT_SPEC.modality == "audio"`.

## Environment — verify, don't assume

Safe defaults if you don't need to check: `librosa` or `torchaudio` for loading/resampling, `soundfile` for I/O, `torch`, `scikit-learn` for splitting/metrics. Prefer `torchaudio` when the pipeline is otherwise torch-native (GPU-resident transforms, no CPU round-trip); `librosa` is fine for CPU-side feature extraction. If the spec names a pretrained speech encoder (e.g. a wav2vec2/whisper-family checkpoint), confirm it exists and check its expected input sample rate with `search_library_docs` — mismatched sample rate is a silent-failure risk here, not an error.

## Pipeline shape

1. Load audio, **resample to a single consistent sample rate first** — see the sample-rate trap below, this has to happen before anything else.
2. Feature extraction: log-mel spectrograms / MFCCs for a CNN pipeline, or the pretrained encoder's own feature extractor if fine-tuning a speech model — don't hand-roll features for a pretrained encoder that ships its own.
3. Handle variable-length clips explicitly: pad/truncate to a fixed window, or use a model architecture that natively handles variable length (e.g. attention-based pooling) — state which you picked and why in a comment.
4. Model: CNN over spectrograms, or fine-tune the pretrained encoder with a task head matching `DATA_SCHEMA.task_type`.
5. Out-of-fold cross-validation — see below.

## Cross-validation

- `StratifiedKFold` for classification — **unless** `DATA_SCHEMA.audio_schema.speaker_id_column` is set, in which case use `GroupKFold` on that column. This is the single most common leakage trap in audio tasks: without it, the model can learn to recognize the *speaker* rather than the thing you're actually trying to predict, and CV looks great while the real leaderboard doesn't.
- Report both `cv_mean` and `cv_std` across folds.
- Print metrics using the required sentinel line:
  ```python
  cv_mean = float(np.mean(fold_scores))
  cv_std = float(np.std(fold_scores))
  print(f'CV_RESULT: {{"cv_mean": {cv_mean:.6f}, "cv_std": {cv_std:.6f}}}')
  ```

## The sample-rate trap

Check `DATA_SCHEMA.audio_schema.sample_rate` before writing any feature-extraction code. If it reports a range rather than a single consistent value, files in the dataset have inconsistent sample rates — resample every file to one target rate (pick the most common rate present, or the pretrained encoder's expected rate if using one) as the very first pipeline step, before feature extraction. Extracting spectrograms/MFCCs from audio at mixed sample rates without normalizing first silently produces features that aren't comparable across examples — this fails quietly, not loudly, so it's worth a defensive comment in the code confirming you handled it.

## Other quality traps

- **Silence/noise imbalance** — if a meaningful fraction of clips are mostly silence or have very different noise floors, consider whether that affects your chosen fixed-window length or normalization; not something to fix unprompted, but worth a comment if you notice it's severe.
- **Channel mismatch** — check `DATA_SCHEMA.audio_schema.channel_count`; if it's `"mixed"`, decide and state explicitly whether you're downmixing to mono or handling channels separately, rather than letting a loader silently pick one behavior.

## Submission format compliance

Match `DATA_SCHEMA`'s sample submission exactly — same columns, same column order, same id dtype, one row per required id. Check this before your final `validate_code` pass, not after.

## Escalate (don't guess) when

- The spec names a pretrained speech encoder that `search_library_docs` can't confirm exists, or whose expected sample rate/input format conflicts with `DATA_SCHEMA.audio_schema`.
- `DATA_SCHEMA.audio_schema.speaker_id_column` is set but the spec's approach gives no indication it accounts for grouped CV — don't silently add `GroupKFold` and call it done; escalate so the Planner's spec reflects it explicitly, unless the spec already clearly intends standard practice and just omitted the detail (use judgment, but when in doubt, flag it).
- The spec's model/window-length/batch-size combination would clearly exceed a resource limit you can see coming.