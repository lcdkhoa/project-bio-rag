"""M0 §2.3 — ĐO bảng màu hộp/sidebar của từng quyển (`box_palette`).

## Vì sao đo, không hardcode

`segmenter.py` tách sidebar / hộp thông tin / hộp hoạt động bằng ngưỡng
`LAYOUT_BOX_MIN_SATURATION` và `pale_sat_min/pale_val_min` — tất cả **đo trên
KNTT**. Một quyển CD/CTST in hộp bằng tông nhạt hơn sẽ tuột hết qua ngưỡng đó, và
segmenter sẽ báo "trang này không có hộp" thay vì báo "ngưỡng của ta sai". Bảng
màu phải là **kết quả đo của từng quyển**.

## Cách đo (CV thuần, không OCR)

1. **"Không phải giấy, không phải mực đen"** = `sat >= SAT_FLOOR` và
   `val >= VAL_FLOOR`. Chọn RỘNG có chủ đích: ngưỡng ở đây chỉ để *tìm ứng viên*,
   còn con số dùng cho segmenter chính là phân bố sat/val mà phép đo này trả về —
   nếu đặt sàn cao thì ta chỉ đo lại được cái sàn của chính mình.
2. Thành phần liên thông sau một close NHỎ (theo tỉ lệ trang). Close nhỏ, không
   phải close lớn: bài học D-32 — `CLOSE(25)` dán khung câu hỏi + panel + mọi ảnh
   thành MỘT blob 39% trang rồi cả cụm bị loại vì không phẳng.
3. Giữ thành phần có diện tích >= `AREA_MIN_FRAC` (2%) **và nền phẳng**, trong đó
   độ phẳng đo trên **đúng pixel của thành phần**, không phải trên bbox — bài học
   D-32 thứ hai: sidebar tím của `page_010` bị loại vì bbox của nó bao cả khe
   trắng.
4. Ghi hue/sat/val trung vị của từng vùng, rồi gộp theo bin hue 10° cho cả quyển.

Phân bố sat/val được ghi ra **theo phân vị** (p05…p95), không chỉ trung vị: một
ngưỡng segmenter cần biết cái đuôi dưới, vì đó là chỗ hộp nhạt nhất bị loại oan.

Không có bước "sửa" và không kết luận thay người: hàm này chỉ trả về SỐ ĐO.
"""

from __future__ import annotations

import statistics
import time

import cv2
import numpy as np

SAT_FLOOR = 8          # dưới mức này là giấy trắng/xám -> không phải tông màu
VAL_FLOOR = 60         # loại chữ đen, viền đen, ảnh tối
AREA_MIN_FRAC = 0.02   # §2.3: "vùng phẳng >= 2% diện tích"
MAX_AREA_FRAC = 0.92   # to hơn thế là nền trang, không phải hộp
CLOSE_FRAC = 0.004     # kernel close theo tỉ lệ chiều rộng trang (KNTT: ~5 px)
UNIFORM_TOL = 40       # khoảng cách L1 tới trung vị vẫn tính là "cùng nền"
UNIFORM_MIN = 0.45     # tỉ lệ pixel gần trung vị -> nền phẳng
HUE_BIN = 10           # OpenCV hue 0..179
SAMPLE_PIXELS = 20_000  # lấy mẫu pixel khi đo trung vị/độ phẳng (vùng có thể 1M px)
_RNG_SEED = 42         # phép đo phải lặp lại được


def _percentiles(values: list) -> dict:
    if not values:
        return {}
    arr = np.asarray(values, dtype=float)
    return {f"p{q:02d}": round(float(np.percentile(arr, q)), 1)
            for q in (5, 10, 25, 50, 75, 90, 95)}


def flat_regions(image_bgr: np.ndarray) -> list:
    """Các vùng nền phẳng có tông màu trên một trang. -> list dict số đo."""
    height, width = image_bgr.shape[:2]
    page_area = float(height * width)
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    sat, val = hsv[:, :, 1], hsv[:, :, 2]
    mask = ((sat >= SAT_FLOOR) & (val >= VAL_FLOOR)).astype(np.uint8)
    k = max(3, int(round(width * CLOSE_FRAC)) | 1)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)

    rng = np.random.default_rng(_RNG_SEED)
    out = []
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        frac = area / page_area
        if frac < AREA_MIN_FRAC or frac > MAX_AREA_FRAC:
            continue
        ys, xs = np.nonzero(labels[y:y + h, x:x + w] == label)
        if ys.size == 0:
            continue
        if ys.size > SAMPLE_PIXELS:
            pick = rng.choice(ys.size, SAMPLE_PIXELS, replace=False)
            ys, xs = ys[pick], xs[pick]
        rows, cols = ys + y, xs + x
        bgr = image_bgr[rows, cols].astype(np.int16)
        med = np.median(bgr, axis=0)
        uniform = float((np.abs(bgr - med).sum(axis=1) < UNIFORM_TOL).mean())
        if uniform < UNIFORM_MIN:
            continue
        hsv_pixels = hsv[rows, cols].astype(np.int16)
        hue_med = float(np.median(hsv_pixels[:, 0]))
        sat_med = float(np.median(hsv_pixels[:, 1]))
        val_med = float(np.median(hsv_pixels[:, 2]))
        out.append({
            "bbox": [int(x), int(y), int(x + w), int(y + h)],
            "area_frac": round(frac, 4),
            "width_frac": round(w / width, 4), "height_frac": round(h / height, 4),
            "hue": round(hue_med, 1), "sat": round(sat_med, 1),
            "val": round(val_med, 1),
            "uniform": round(uniform, 3),
        })
    return out


def probe_box_palette(source, pages: list, verbose: bool = False) -> dict:
    """Bảng màu hộp của một quyển, đo trên `pages`."""
    t0 = time.time()
    regions: list = []
    per_page: list = []
    page_width = None
    for pn in pages:
        image = source.load(pn)
        page_width = image.shape[1]
        found = flat_regions(image)
        for r in found:
            r["page"] = pn
        regions.extend(found)
        per_page.append(len(found))

    bins: dict = {}
    for r in regions:
        key = int(r["hue"]) // HUE_BIN
        bins.setdefault(key, []).append(r)

    bands = []
    for key in sorted(bins, key=lambda k: -len(bins[k])):
        group = bins[key]
        bands.append({
            "hue_lo": key * HUE_BIN, "hue_hi": (key + 1) * HUE_BIN - 1,
            "n": len(group),
            "sat_median": round(statistics.median(g["sat"] for g in group), 1),
            "val_median": round(statistics.median(g["val"] for g in group), 1),
            "area_frac_median": round(
                statistics.median(g["area_frac"] for g in group), 4),
            "width_frac_median": round(
                statistics.median(g["width_frac"] for g in group), 3),
            "pages": sorted({g["page"] for g in group})[:5],
        })

    flags = []
    if not regions:
        flags.append("khong_do_duoc_vung_phang_nao")
    elif len(bands) == 1:
        flags.append("chi_mot_dai_hue — kiem lai xem co phai nen trang khong")

    out = {
        "pages_probed": pages,
        "n_regions": len(regions),
        "regions_per_page": round(len(regions) / len(pages), 2) if pages else 0.0,
        "pages_with_no_region": [pn for pn, n in zip(pages, per_page) if n == 0],
        "hue_bands": bands,
        "sat_percentiles": _percentiles([r["sat"] for r in regions]),
        "val_percentiles": _percentiles([r["val"] for r in regions]),
        "area_frac_percentiles": _percentiles([r["area_frac"] for r in regions]),
        "thresholds_used": {"sat_floor": SAT_FLOOR, "val_floor": VAL_FLOOR,
                            "area_min_frac": AREA_MIN_FRAC,
                            "uniform_min": UNIFORM_MIN,
                            "page_width": page_width,
                            "close_kernel_px": (
                                max(3, int(round(page_width * CLOSE_FRAC)) | 1)
                                if page_width else None)},
        "examples": regions[:12],
        "seconds": round(time.time() - t0, 1),
        "flags": flags,
    }
    if verbose:
        print(f"    [palette] {len(regions)} vung / {len(pages)} trang, "
              f"{len(bands)} dai hue, sat p10={out['sat_percentiles'].get('p10')} "
              f"({out['seconds']}s)")
    return out
