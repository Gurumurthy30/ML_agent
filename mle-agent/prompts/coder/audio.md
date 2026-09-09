# Audio Modality Coder Guidelines

1. Use standard Audio libraries: `librosa`, `torchaudio`, `soundfile`, `torch`, `scikit-learn`.
2. Pipeline: Audio loading, feature extraction (MFCCs / Mel-Spectrograms), model training with cross-validation.
3. Save predictions to `submission.csv`.
