# Computer Vision Modality Coder Guidelines

1. Use standard CV libraries: `torch`, `torchvision`, `timm`, `albumentations`, `PIL`, `cv2`.
2. Pipeline: Data loading with Dataset/DataLoader, image transformations, model initialization (e.g. `timm.create_model`), training loop with mixed precision (`torch.cuda.amp`), and out-of-fold validation.
3. Save predictions to `submission.csv`.
