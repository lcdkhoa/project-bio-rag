"""Image ETL pipeline for scanned PDFs with CLIP-based filtering."""

import hashlib
import io
import json
import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from PIL import Image
from langchain_core.documents import Document
from pdf2image import convert_from_path
from transformers import CLIPModel, CLIPProcessor
from tqdm import tqdm

from ..config import (
    CLIP_MODEL,
    HF_TOKEN,
    IMAGE_EXTRACTION_VERSION,
    IMAGE_REVIEW_MANIFEST_PATH,
    IMAGES_DIR,
)
from .image_captioner import ImageCaptioner
from .processing_status import ProcessingStatus, compute_file_hash

logger = logging.getLogger(__name__)

CLIP_ZERO_SHOT_PROMPT = (
    "a photograph, a scientific diagram, an illustration of biology, "
    "a biology diagram, a textbook infographic with an illustration, a cell, "
    "an organ, a microscope view, an experiment setup"
)

CLIP_NEGATIVE_PROMPT = (
    "empty page, white space, pure color background, decorative border, "
    "plain text without any illustration"
)

VIETNAMESE_STOPWORDS = {
    "anh",
    "bang",
    "cac",
    "cho",
    "co",
    "cua",
    "duoc",
    "hay",
    "hinh",
    "khi",
    "la",
    "lam",
    "mot",
    "nay",
    "nhung",
    "o",
    "quan",
    "sat",
    "sgk",
    "the",
    "thi",
    "trang",
    "trong",
    "tu",
    "va",
    "ve",
    "voi",
}


class ImageProcessor:
    """Extract, filter, and enrich images from scanned PDFs using Vietnamese page context."""

    def __init__(self, status_tracker: Optional[ProcessingStatus] = None):
        self.status_tracker = status_tracker or ProcessingStatus()
        self._clip_model: Optional[CLIPModel] = None
        self._clip_processor: Optional[CLIPProcessor] = None
        self.captioner = ImageCaptioner()
        self.image_extraction_version = IMAGE_EXTRACTION_VERSION
        self.review_manifest_path = IMAGE_REVIEW_MANIFEST_PATH

    @property
    def clip_model(self) -> CLIPModel:
        if self._clip_model is None:
            logger.info(f"Loading CLIP model: {CLIP_MODEL}")
            self._clip_model = CLIPModel.from_pretrained(CLIP_MODEL, token=HF_TOKEN)
            self._clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL, token=HF_TOKEN)
            logger.info("CLIP model loaded")
        return self._clip_model

    @property
    def clip_processor(self) -> CLIPProcessor:
        if self._clip_processor is None:
            _ = self.clip_model
        return self._clip_processor

    def _detect_contour_regions(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Recall-first region proposal using multiple detectors."""
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        regions: List[Tuple[int, int, int, int]] = []

        # Strategy 1: contour on inverse threshold.
        thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)[1]
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if cv2.contourArea(contour) < 850:
                continue
            regions.append((x, y, x + w, y + h))

        # Strategy 2: connected components for separated media blocks.
        comp_bin = cv2.adaptiveThreshold(
            gray,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            8,
        )
        num_labels, _, stats, _ = cv2.connectedComponentsWithStats(comp_bin, connectivity=8)
        for label in range(1, num_labels):
            x, y, w, h, area = stats[label]
            if area < 1400 or w < 48 or h < 48:
                continue
            regions.append((x, y, x + w, y + h))

        # Strategy 3: edge-preserving rectangular hints.
        edges = cv2.Canny(gray, 60, 150)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edge_mask = cv2.dilate(edges, kernel, iterations=1)
        edge_contours, _ = cv2.findContours(edge_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in edge_contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < 70 or h < 70:
                continue
            regions.append((x, y, x + w, y + h))

        # Strategy 4: high-saturation blocks (helps separate colorful textbook photos).
        hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
        sat_mask = cv2.inRange(hsv, np.array([0, 32, 35]), np.array([180, 255, 252]))
        sat_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        sat_mask = cv2.morphologyEx(sat_mask, cv2.MORPH_CLOSE, sat_kernel, iterations=2)
        sat_mask = cv2.morphologyEx(sat_mask, cv2.MORPH_OPEN, sat_kernel, iterations=1)
        sat_contours, _ = cv2.findContours(sat_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sat_contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < 90 or h < 90:
                continue
            regions.append((x, y, x + w, y + h))

        return self._deduplicate_regions(regions, image.shape[1], image.shape[0])

    def _bbox_area(self, bbox: Tuple[int, int, int, int]) -> int:
        x0, y0, x1, y1 = bbox
        return max(0, x1 - x0) * max(0, y1 - y0)

    def _expand_bbox(
        self,
        bbox: Tuple[int, int, int, int],
        width: int,
        height: int,
        ratio: float = 0.012,
    ) -> Tuple[int, int, int, int]:
        x0, y0, x1, y1 = bbox
        pad_x = max(4, int((x1 - x0) * ratio))
        pad_y = max(4, int((y1 - y0) * ratio))
        return (
            max(0, x0 - pad_x),
            max(0, y0 - pad_y),
            min(width, x1 + pad_x),
            min(height, y1 + pad_y),
        )

    def _iou(self, left: Tuple[int, int, int, int], right: Tuple[int, int, int, int]) -> float:
        lx0, ly0, lx1, ly1 = left
        rx0, ry0, rx1, ry1 = right
        ix0, iy0 = max(lx0, rx0), max(ly0, ry0)
        ix1, iy1 = min(lx1, rx1), min(ly1, ry1)
        inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
        if inter == 0:
            return 0.0
        union = self._bbox_area(left) + self._bbox_area(right) - inter
        return inter / union if union > 0 else 0.0

    def _contains(self, outer: Tuple[int, int, int, int], inner: Tuple[int, int, int, int]) -> bool:
        ox0, oy0, ox1, oy1 = outer
        ix0, iy0, ix1, iy1 = inner
        return ox0 <= ix0 and oy0 <= iy0 and ox1 >= ix1 and oy1 >= iy1

    def _deduplicate_regions(
        self,
        regions: List[Tuple[int, int, int, int]],
        page_width: int,
        page_height: int,
    ) -> List[Tuple[int, int, int, int]]:
        deduped: List[Tuple[int, int, int, int]] = []
        for raw_bbox in regions:
            bbox = self._expand_bbox(raw_bbox, page_width, page_height)
            if self._bbox_area(bbox) < 2000:
                continue

            replaced = False
            for index, kept in enumerate(deduped):
                overlap = self._iou(bbox, kept)
                if overlap >= 0.72:
                    if self._bbox_area(bbox) > self._bbox_area(kept):
                        deduped[index] = bbox
                    replaced = True
                    break
                if self._contains(kept, bbox) or self._contains(bbox, kept):
                    area_left = self._bbox_area(kept)
                    area_right = self._bbox_area(bbox)
                    ratio = (max(area_left, area_right) / max(1, min(area_left, area_right)))
                    if ratio <= 1.8:
                        if area_right > area_left:
                            deduped[index] = bbox
                        replaced = True
                        break
            if not replaced:
                deduped.append(bbox)
        return deduped

    def _suppress_container_regions(
        self,
        regions: List[Tuple[int, int, int, int]],
        page_width: int,
        page_height: int,
    ) -> List[Tuple[int, int, int, int]]:
        if len(regions) <= 1:
            return regions

        kept: List[Tuple[int, int, int, int]] = []
        for bbox in regions:
            area = self._bbox_area(bbox)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            contained_children = 0
            overlap_children = 0

            for other in regions:
                if other == bbox:
                    continue
                if not self._contains(bbox, other):
                    overlap_ratio = self._iou(bbox, other)
                    if overlap_ratio >= 0.18 and self._bbox_area(other) < area * 0.7:
                        overlap_children += 1
                    continue
                if self._bbox_area(other) >= area * 0.12:
                    contained_children += 1

            is_wide_container = (width / max(1, page_width)) > 0.88 and (height / max(1, page_height)) < 0.26
            has_multiple_children = contained_children >= 2
            if is_wide_container and (contained_children >= 1 or overlap_children >= 2):
                continue
            if (has_multiple_children or overlap_children >= 3) and area > (page_width * page_height * 0.08):
                continue

            kept.append(bbox)

        return kept

    def _limit_regions_for_extraction(
        self,
        regions: List[Tuple[int, int, int, int]],
        max_regions: int = 24,
    ) -> List[Tuple[int, int, int, int]]:
        if len(regions) <= max_regions:
            return [(int(x0), int(y0), int(x1), int(y1)) for x0, y0, x1, y1 in regions]

        ranked = sorted(
            [(int(x0), int(y0), int(x1), int(y1)) for x0, y0, x1, y1 in regions],
            key=lambda bbox: self._bbox_area(bbox),
            reverse=True,
        )
        selected: List[Tuple[int, int, int, int]] = []
        for bbox in ranked:
            if any(self._iou(bbox, kept) > 0.58 for kept in selected):
                continue
            selected.append(bbox)
            if len(selected) >= max_regions:
                break

        if len(selected) < max_regions:
            for bbox in ranked:
                if bbox in selected:
                    continue
                selected.append(bbox)
                if len(selected) >= max_regions:
                    break
        return selected

    def _check_color_variance(self, image: np.ndarray, bbox: Tuple[int, int, int, int]) -> bool:
        """Check if a region has sufficient color variance to be a real image."""
        x0, y0, x1, y1 = bbox
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(image.shape[1], x1), min(image.shape[0], y1)

        if x1 <= x0 or y1 <= y0:
            return False

        region = image[y0:y1, x0:x1]
        if region.size == 0:
            return False

        hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
        h_std = np.std(hsv[:, :, 0])
        s_std = np.std(hsv[:, :, 1])
        v_std = np.std(hsv[:, :, 2])

        total_variance = h_std + s_std + v_std
        return total_variance > 15

    def _refine_regions(self, regions: List[Tuple[int, int, int, int]], image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Recall-first filtering: keep candidate image blocks, remove obvious noise."""
        page_height, page_width = image.shape[0], image.shape[1]
        page_area = page_width * page_height
        refined = []
        for bbox in regions:
            x0, y0, x1, y1 = bbox
            width = x1 - x0
            height = y1 - y0
            area = width * height

            aspect_ratio = width / height if height > 0 else 0
            if aspect_ratio < 0.12 or aspect_ratio > 12:
                continue

            if width < 45 or height < 45:
                continue

            # Reject very tiny icons and over-large whole-page text blocks.
            if area < 2200:
                continue
            if area > page_area * 0.75:
                continue

            # Keep low-variance regions if they are reasonably large (useful for grayscale figures).
            if area < page_area * 0.05 and not self._check_color_variance(image, bbox):
                continue

            edge_margin = int(min(page_width, page_height) * 0.012)
            if x0 <= edge_margin and y0 <= edge_margin and width < 170 and height < 170:
                continue

            refined.append(bbox)

        refined.sort(key=lambda item: self._bbox_area(item), reverse=True)
        deduped = self._deduplicate_regions(refined, page_width, page_height)
        return self._suppress_container_regions(deduped, page_width, page_height)

    def _clip_filter(self, image: Image.Image) -> Tuple[bool, float, float]:
        """Zero-shot CLIP classification to keep only photograph/diagram/illustration."""
        try:
            inputs = self.clip_processor(
                text=[CLIP_ZERO_SHOT_PROMPT, CLIP_NEGATIVE_PROMPT],
                images=image,
                return_tensors="pt",
                padding=True,
            )

            with torch.no_grad():
                outputs = self.clip_model(**inputs)
                logits_per_image = outputs.logits_per_image
                probs = logits_per_image.softmax(dim=1)

            pos_prob = probs[0][0].item()
            neg_prob = probs[0][1].item()

            visual_score = self._visual_content_score(image)
            keep = pos_prob > neg_prob or (visual_score > 0.04 and neg_prob < 0.72)
            logger.debug(
                f"CLIP filter: pos={pos_prob:.3f}, neg={neg_prob:.3f}, visual={visual_score:.3f}, keep={keep}"
            )
            return keep, pos_prob, neg_prob
        except Exception as e:
            logger.warning(f"CLIP filter failed: {e}, keeping image by default")
            return True, 0.0, 0.0

    def _visual_content_score(self, image: Image.Image) -> float:
        """Estimate how much non-background colored visual content a crop contains."""
        img_array = np.array(image.convert("RGB"))
        hsv = cv2.cvtColor(img_array, cv2.COLOR_RGB2HSV)
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]
        colored_pixels = (saturation > 45) & (value > 40) & (value < 252)
        return float(np.mean(colored_pixels))

    def _extract_page_image(self, pdf_path: str, page_num: int) -> Optional[Tuple[np.ndarray, Image.Image]]:
        """Render a PDF page as image for extraction."""
        try:
            images = convert_from_path(pdf_path, first_page=page_num + 1, last_page=page_num + 1, dpi=150)
            if images:
                img_array = np.array(images[0])
                return img_array, images[0]
        except Exception as e:
            logger.warning(f"Failed to render page {page_num}: {e}")
        return None

    def _get_context_text(self, pdf_path: str, page_num: int, bbox: Tuple[int, int, int, int], page_text: str) -> str:
        """Extract text within region around the image using OCR."""
        try:
            import pytesseract

            images = convert_from_path(pdf_path, first_page=page_num + 1, last_page=page_num + 1, dpi=150)
            if not images:
                return page_text[:500] if page_text else ""

            img = images[0]
            x0, y0, x1, y1 = bbox

            h, w = img.height, img.width
            y0_pad = max(0, y0 - int(h * 0.05))
            y1_pad = min(h, y1 + int(h * 0.05))

            padded_img = img.crop((0, y0_pad, w, y1_pad))
            context = pytesseract.image_to_string(padded_img, lang="vie")
            return context.strip()[:500]
        except Exception:
            return page_text[:500] if page_text else ""

    def _ocr_crop_text(self, image: Image.Image) -> str:
        """OCR only the crop itself so text-heavy regions can be identified."""
        try:
            import pytesseract

            text = pytesseract.image_to_string(image, lang="vie")
            return self._clean_text(text, max_chars=300)
        except Exception:
            return ""

    def _normalize_text(self, text: str) -> str:
        text = unicodedata.normalize("NFD", text.lower())
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        return re.sub(r"[^a-z0-9\s]+", " ", text)

    def _clean_text(self, text: str, max_chars: int = 1200) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        return text[:max_chars]

    def _extract_section_title(self, page_text: str) -> str:
        """Find a compact lesson or section title from page OCR/PDF text."""
        lines = [line.strip() for line in (page_text or "").splitlines() if line.strip()]
        title_candidates = []
        for line in lines[:30]:
            normalized = self._normalize_text(line)
            if len(line) > 90 or len(line) < 4:
                continue
            if re.match(r"^(\d+[\.\)]|[ivx]+\.)\s+", normalized) or line.isupper():
                title_candidates.append(line)
            elif any(keyword in normalized for keyword in ("bai ", "chu de", "cac lop", "su da dang")):
                title_candidates.append(line)

        return title_candidates[-1] if title_candidates else ""

    def _extract_lesson_title(self, page_text: str) -> str:
        """Find a coarse lesson title for page-level metadata."""
        lines = [line.strip() for line in (page_text or "").splitlines() if line.strip()]
        for index, line in enumerate(lines[:35]):
            normalized = self._normalize_text(line)
            if re.search(r"\bbai\s+\d+", normalized):
                next_line = lines[index + 1] if index + 1 < len(lines) else ""
                combined = f"{line} {next_line}".strip()
                return self._clean_text(combined, max_chars=140)
        return ""

    def _extract_figure_label(self, context_text: str, page_text: str) -> str:
        """Extract labels that are meaningful in Vietnamese textbooks."""
        text = f"{context_text}\n{page_text}"
        patterns = [
            r"Em\s+c[oó]\s+bi[eế]t",
            r"T[iì]m\s+hi[eể]u\s+th[eê]m",
            r"Quan\s+s[aá]t",
            r"B[aả]ng\s+\d+(?:\.\d+)?",
            r"H[iì]nh\s+\d+(?:\.\d+)?",
            r"Th[uư]c\s+h[aà]nh",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(0)
        return ""

    def _extract_figure_caption(self, context_text: str, page_text: str) -> str:
        """Extract a compact figure/table caption instead of using the whole page context."""
        text = f"{context_text}\n{page_text}"
        patterns = [
            r"(H[iì]nh\s+\d+(?:\.\d+)?[\.:]?\s*[^\n]{0,180})",
            r"(B[aả]ng\s+\d+(?:\.\d+)?[\.:]?\s*[^\n]{0,180})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return self._clean_text(match.group(1), max_chars=220)
        return ""

    def _infer_image_type(self, figure_label: str, context_text: str, crop_text: str = "") -> str:
        normalized = self._normalize_text(f"{figure_label} {context_text}")
        crop_normalized = self._normalize_text(crop_text)
        crop_tokens = [token for token in crop_normalized.split() if len(token) > 1]
        if len(crop_tokens) >= 2 and len(crop_tokens) <= 12 and not figure_label:
            return "text_crop"
        if "em co biet" in normalized:
            return "textbook_info_box"
        if "tim hieu them" in normalized or "quan sat" in normalized or "thuc hanh" in normalized:
            return "activity_box"
        if "bang" in normalized:
            return "table"
        if "hinh" in normalized:
            return "figure"
        return "image_region"

    def _is_text_dominant_crop(
        self,
        crop: Image.Image,
        crop_text: str,
        clip_positive_score: float,
        clip_negative_score: float,
    ) -> bool:
        """Reject standalone headings/labels that contour detection mistakes for figures."""
        normalized = self._normalize_text(crop_text)
        tokens = [token for token in normalized.split() if len(token) > 1]
        if len(tokens) < 2:
            return False

        visual_score = self._visual_content_score(crop)
        aspect_ratio = crop.width / crop.height if crop.height else 0
        crop_area = crop.width * crop.height
        short_text = len(tokens) <= 10 and len(normalized) <= 80
        weak_visual = visual_score < 0.055 and clip_negative_score >= (clip_positive_score + 0.06)
        return short_text and weak_visual and aspect_ratio < 9 and crop_area < 120000

    def _extract_keywords(self, *texts: str, limit: int = 18) -> str:
        """Extract lightweight Vietnamese keyword metadata without calling another model."""
        normalized = self._normalize_text(" ".join(texts))
        tokens = [token for token in normalized.split() if len(token) > 1 and token not in VIETNAMESE_STOPWORDS]

        scores: Dict[str, int] = {}
        for token in tokens:
            scores[token] = scores.get(token, 0) + 1

        for left, right in zip(tokens, tokens[1:]):
            phrase = f"{left} {right}"
            scores[phrase] = scores.get(phrase, 0) + 2

        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        return ", ".join(keyword for keyword, _ in ranked[:limit])

    def _save_page_snapshot(self, output_dir: Path, page_num: int, page_image: Image.Image) -> str:
        """Save a deterministic page snapshot for fallback/debug metadata."""
        snapshot_dir = output_dir / "pages"
        os.makedirs(snapshot_dir, exist_ok=True)
        snapshot_path = snapshot_dir / f"page_{page_num}_snapshot.png"
        if not snapshot_path.exists():
            page_image.save(snapshot_path, format="PNG")
        return str(snapshot_path)

    def _compute_image_hash(self, image_data: bytes) -> str:
        """Compute MD5 hash for deduplication."""
        return hashlib.md5(image_data).hexdigest()

    def _resolve_image_path(self, output_dir: Path, page_num: int, img_index: int, img_hash: str) -> Path:
        """Return a deterministic image path and avoid duplicate files on reprocessing."""
        filepath = output_dir / f"page_{page_num}_img_{img_index}.png"
        if not filepath.exists():
            return filepath

        try:
            existing_hash = self._compute_image_hash(filepath.read_bytes())
            if existing_hash == img_hash:
                return filepath
        except Exception as e:
            logger.debug(f"Could not hash existing image {filepath}: {e}")

        hash_path = output_dir / f"page_{page_num}_img_{img_index}_{img_hash[:8]}.png"
        if not hash_path.exists():
            return hash_path

        try:
            existing_hash = self._compute_image_hash(hash_path.read_bytes())
            if existing_hash == img_hash:
                return hash_path
        except Exception as e:
            logger.debug(f"Could not hash existing image {hash_path}: {e}")

        attempt = 1
        while True:
            candidate = output_dir / f"page_{page_num}_img_{img_index}_{img_hash[:8]}_{attempt}.png"
            if not candidate.exists():
                return candidate
            attempt += 1

    def _build_image_id(
        self,
        pdf_hash: str,
        page_num: int,
        bbox: Tuple[int, int, int, int],
        image_hash: str,
    ) -> str:
        payload = f"{pdf_hash}:{page_num}:{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}:{image_hash}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    def _append_review_manifest(self, metadata: Dict[str, object]) -> None:
        try:
            self.review_manifest_path.parent.mkdir(parents=True, exist_ok=True)
            record = dict(metadata)
            record["manifest_written_at"] = datetime.now().isoformat()
            with self.review_manifest_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Could not append image manifest: {e}")

    def _build_image_search_text(self, metadata: Dict[str, object]) -> str:
        """Build Vietnamese-first text used to retrieve this image later."""
        caption_text = metadata.get("caption_vi_manual", "") or metadata.get("caption_vi", "") or metadata.get("caption", "")
        keywords_text = metadata.get("keywords_vi_manual", "") or metadata.get("keywords_vi", "")
        parts = [
            metadata.get("figure_label", ""),
            metadata.get("figure_caption", ""),
            metadata.get("section_title", ""),
            metadata.get("image_type", ""),
            keywords_text,
            caption_text,
            metadata.get("context_text", ""),
            f"Trang {metadata.get('page_number', '')}",
            metadata.get("pdf_filename", ""),
        ]
        return "\n".join(part.strip() for part in parts if part and part.strip())

    def extract_images_from_pdf(
        self,
        pdf_path: str,
        pdf_hash: str,
        pdf_filename: str,
        ocr_text_per_page: Dict[int, str],
        force: bool = False,
    ) -> List[Document]:
        """
        Full image ETL pipeline for a single PDF.

        Phase 1: Contour detection for region discovery
        Phase 2: Refinement (color variance + aspect ratio)
        Phase 3: CLIP zero-shot filtering
        Phase 4: Vietnamese OCR/context metadata + storage
        """
        extracted_docs = []
        output_dir = IMAGES_DIR / Path(pdf_filename).stem
        os.makedirs(output_dir, exist_ok=True)

        import fitz

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        doc.close()

        for page_num in tqdm(range(1, total_pages + 1), desc=f"[{pdf_filename}] Extracting images"):
            if not force and not self.status_tracker.needs_image_processing_versioned(
                pdf_hash,
                page_num,
                required_version=self.image_extraction_version,
            ):
                logger.debug(f"Page {page_num}: already processed, skipping")
                continue

            page_result = self._extract_page_image(pdf_path, page_num - 1)
            if not page_result:
                continue

            img_array, pil_img = page_result
            page_text = ocr_text_per_page.get(page_num, "")
            nearby_text = self._clean_text(page_text, max_chars=1600)
            lesson_title = self._extract_lesson_title(page_text)
            section_title = self._extract_section_title(page_text)
            page_snapshot_path = self._save_page_snapshot(output_dir, page_num, pil_img)

            regions = self._detect_contour_regions(img_array)
            refined = self._refine_regions(regions, img_array)
            refined = self._limit_regions_for_extraction(refined, max_regions=24)

            logger.debug(f"Page {page_num}: detected {len(regions)} regions, {len(refined)} after refinement")

            img_index = 0
            page_seen_hashes = set()
            for bbox in refined:
                x0, y0, x1, y1 = bbox
                crop = pil_img.crop((x0, y0, x1, y1))

                if crop.width < 50 or crop.height < 50:
                    continue

                keep_crop, clip_positive_score, clip_negative_score = self._clip_filter(crop)
                if not keep_crop:
                    logger.debug(f"Page {page_num} img {img_index}: filtered out by CLIP")
                    img_index += 1
                    continue

                crop_text = self._ocr_crop_text(crop)
                if self._is_text_dominant_crop(crop, crop_text, clip_positive_score, clip_negative_score):
                    logger.debug(f"Page {page_num} img {img_index}: filtered out as text-dominant crop")
                    img_index += 1
                    continue

                img_bytes = io.BytesIO()
                crop.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                img_data = img_bytes.read()

                img_hash = self._compute_image_hash(img_data)
                if img_hash in page_seen_hashes:
                    logger.debug(f"Page {page_num} img {img_index}: duplicate hash, skipping")
                    img_index += 1
                    continue
                page_seen_hashes.add(img_hash)

                image_id = self._build_image_id(pdf_hash, page_num, bbox, img_hash)
                visual_metadata = self.captioner.caption(crop, img_hash)

                filepath = self._resolve_image_path(output_dir, page_num, img_index, img_hash)

                with open(filepath, "wb") as f:
                    f.write(img_data)

                context_text = self._get_context_text(pdf_path, page_num, bbox, page_text)
                context_text = self._clean_text(context_text, max_chars=1200)
                local_text = "\n".join(part for part in (context_text, crop_text) if part)
                figure_label = self._extract_figure_label(local_text, "")
                figure_caption = self._extract_figure_caption(local_text, "")
                image_type = self._infer_image_type(figure_label, context_text, crop_text)
                visual_caption = visual_metadata.get("visual_caption_vi", "")
                visual_keywords = visual_metadata.get("visual_keywords_vi", "")
                visual_objects = visual_metadata.get("visual_objects_vi", "")
                keywords_vi = self._extract_keywords(
                    lesson_title,
                    section_title,
                    figure_label,
                    figure_caption,
                    visual_caption,
                    visual_keywords,
                    visual_objects,
                    context_text,
                    crop_text,
                )
                caption_text = visual_caption or figure_caption or context_text[:240]

                metadata = {
                    "image_id": image_id,
                    "image_path": str(filepath),
                    "page_snapshot_path": page_snapshot_path,
                    "image_hash": img_hash,
                    "page_number": page_num,
                    "pdf_hash": pdf_hash,
                    "pdf_filename": pdf_filename,
                    "lesson_title": lesson_title,
                    "section_title": section_title,
                    "figure_label": figure_label,
                    "figure_caption": figure_caption,
                    **visual_metadata,
                    "image_type": image_type,
                    "keywords_vi": keywords_vi,
                    "caption": caption_text,
                    "caption_vi": caption_text,
                    "caption_vi_manual": "",
                    "context_text": context_text,
                    "crop_text": crop_text,
                    "nearby_text": nearby_text,
                    "review_status": "pending",
                    "is_active": True,
                    "review_notes": "",
                    "reviewed_by": "",
                    "reviewed_at": "",
                    "keywords_vi_manual": "",
                    "final_caption_vi": caption_text,
                    "final_keywords_vi": keywords_vi,
                    "extraction_version": self.image_extraction_version,
                    "bbox": ",".join(str(value) for value in bbox),
                    "image_width": crop.width,
                    "image_height": crop.height,
                    "visual_content_score": round(self._visual_content_score(crop), 4),
                    "clip_positive_score": round(clip_positive_score, 4),
                    "clip_negative_score": round(clip_negative_score, 4),
                }
                search_text = self._build_image_search_text(metadata)
                metadata["search_text"] = search_text

                doc = Document(page_content=search_text, metadata=metadata)
                extracted_docs.append(doc)
                self._append_review_manifest(metadata)

                logger.debug(f"Saved: {filepath} (label={figure_label or image_type}, keywords={keywords_vi[:80]})")
                img_index += 1

            self.status_tracker.mark_image_extracted(
                pdf_hash,
                page_num,
                pdf_filename,
                image_extraction_version=self.image_extraction_version,
            )

        logger.info(f"[{pdf_filename}] Extracted {len(extracted_docs)} images from {total_pages} pages")
        return extracted_docs
