"""Page cleanup before segmentation: watermark/stamp masking (deskew stub)."""
import numpy as np

# Fraction of page width occupied by the KNTT left-margin personal stamp.
KNTT_STAMP_FRAC = 0.06

def preprocess_page(image: np.ndarray, variant: str) -> np.ndarray:
    out = image.copy()
    h, w = out.shape[:2]
    if variant == "kntt":
        band = max(1, int(w * KNTT_STAMP_FRAC))
        out[:, 0:band] = 255  # wipe left-margin stamp to page white
    # deskew: intentional no-op in M1 (scans are near-upright); revisit if QA shows skew.
    return out
