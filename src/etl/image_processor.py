"""Image ETL pipeline for scanned PDFs with OWL-ViT region detection."""

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
from transformers import OwlViTForObjectDetection, OwlViTProcessor
from tqdm import tqdm

from ..config import (
    HF_TOKEN,
    IMAGE_EXTRACTION_VERSION,
    IMAGE_REVIEW_MANIFEST_PATH,
    IMAGES_DIR,
    OWL_VIT_CONFIDENCE_THRESHOLD,
    OWL_VIT_MODEL,
    POPPLER_PATH,
    TESSERACT_CMD,
    USE_GPU,
)
from .image_captioner import ImageCaptioner
from .processing_status import ProcessingStatus, compute_file_hash

logger = logging.getLogger(__name__)

OWL_VIT_TEXT_QUERIES = [
    "a scientific formula",
    "a biology diagram",
    "a textbook illustration",
    "a data table",
    "a chart or graph",
    "a science experiment setup",
    "a microscope image",
    "a photo in a textbook",
    "a framed textbook picture",
    "a material sample photo",
    "an object photo",
    "a framed object photo",
    "a product-style object photo",
    "an isolated object on white background",
    "a bowl of liquid",
    "a sample of raw material",
    "a coil of wire",
]

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
        self._owlvit_model: Optional[OwlViTForObjectDetection] = None
        self._owlvit_processor: Optional[OwlViTProcessor] = None
        self._owlvit_device = "cuda" if USE_GPU and torch.cuda.is_available() else "cpu"
        self.captioner = ImageCaptioner()
        self.image_extraction_version = IMAGE_EXTRACTION_VERSION
        self.review_manifest_path = IMAGE_REVIEW_MANIFEST_PATH

    @property
    def owlvit_model(self) -> OwlViTForObjectDetection:
        if self._owlvit_model is None:
            logger.info(f"Loading OWL-ViT detector: {OWL_VIT_MODEL}")
            self._owlvit_model = OwlViTForObjectDetection.from_pretrained(
                OWL_VIT_MODEL,
                token=HF_TOKEN if HF_TOKEN else None,
            )
            self._owlvit_processor = OwlViTProcessor.from_pretrained(
                OWL_VIT_MODEL,
                token=HF_TOKEN if HF_TOKEN else None,
            )
            self._owlvit_model.to(self._owlvit_device)
            self._owlvit_model.eval()
            logger.info(f"OWL-ViT detector loaded on {self._owlvit_device}")
        return self._owlvit_model

    @property
    def owlvit_processor(self) -> OwlViTProcessor:
        if self._owlvit_processor is None:
            _ = self.owlvit_model
        return self._owlvit_processor

    def _detect_contour_regions(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Open-vocabulary region proposal. Kept for compatibility with older callers."""
        pil_image = Image.fromarray(image).convert("RGB")
        return self._detect_regions_with_owlvit(pil_image, OWL_VIT_TEXT_QUERIES)

    def _detect_regions_with_owlvit(
        self,
        image: Image.Image,
        text_queries: List[str],
        threshold: float = OWL_VIT_CONFIDENCE_THRESHOLD,
    ) -> List[Tuple[int, int, int, int]]:
        """Detect textbook visual regions with OWL-ViT zero-shot object detection."""
        try:
            rgb_image = image.convert("RGB")
            inputs = self.owlvit_processor(
                text=[text_queries],
                images=rgb_image,
                return_tensors="pt",
            )
            inputs = {
                key: value.to(self._owlvit_device) if hasattr(value, "to") else value
                for key, value in inputs.items()
            }

            with torch.no_grad():
                outputs = self.owlvit_model(**inputs)

            target_sizes = torch.tensor(
                [rgb_image.size[::-1]],
                dtype=torch.float,
                device=self._owlvit_device,
            )
            post_process_object_detection = getattr(
                self.owlvit_processor, "post_process_object_detection", None)
            if post_process_object_detection:
                results = post_process_object_detection(
                    outputs=outputs,
                    target_sizes=target_sizes,
                    threshold=threshold,
                )[0]
            else:
                results = self.owlvit_processor.post_process_grounded_object_detection(
                    outputs=outputs,
                    threshold=threshold,
                    target_sizes=target_sizes,
                    text_labels=[text_queries],
                )[0]

            page_width, page_height = rgb_image.size
            page_area = page_width * page_height
            regions: List[Tuple[int, int, int, int]] = []
            labels = results.get("labels", results.get("text_labels", []))
            for score, label, box in zip(
                results.get("scores", []),
                labels,
                results.get("boxes", []),
            ):
                x0, y0, x1, y1 = [int(round(value)) for value in box.tolist()]
                bbox = (
                    max(0, min(page_width, x0)),
                    max(0, min(page_height, y0)),
                    max(0, min(page_width, x1)),
                    max(0, min(page_height, y1)),
                )
                if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                    continue
                if self._bbox_area(bbox) > page_area * 0.82:
                    continue
                regions.append(bbox)
                label_value = label.item() if hasattr(label, "item") else label
                if isinstance(label_value, int) and label_value < len(text_queries):
                    query = text_queries[label_value]
                else:
                    query = str(label_value)
                logger.debug(
                    f"OWL-ViT detection: query={query!r}, score={float(score):.3f}, bbox={bbox}"
                )

            return regions
        except Exception as e:
            logger.warning(f"OWL-ViT detection failed: {e}")
            return []

    def _detect_framed_regions(self, image: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """Find textbook picture panels from cyan/green frame strokes that OWL-ViT can miss."""
        try:
            page_height, page_width = image.shape[0], image.shape[1]
            page_area = page_width * page_height
            hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)

            # Vietnamese textbooks often use thin cyan/green rounded rectangles around sub-figures.
            frame_mask = cv2.inRange(
                hsv,
                np.array([70, 35, 65]),
                np.array([105, 255, 255]),
            )
            close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 13))
            frame_mask = cv2.dilate(frame_mask, close_kernel, iterations=1)
            frame_mask = cv2.morphologyEx(
                frame_mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)

            contours, _ = cv2.findContours(
                frame_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            regions: List[Tuple[int, int, int, int]] = []
            for contour in contours:
                x, y, width, height = cv2.boundingRect(contour)
                area = width * height
                if width < 110 or height < 70:
                    continue
                if area < 9000 or area > page_area * 0.35:
                    continue

                aspect_ratio = width / height if height else 0
                if aspect_ratio < 0.45 or aspect_ratio > 4.2:
                    continue

                is_wide_header = width > page_width * 0.62 and height < page_height * 0.14
                if is_wide_header and y < page_height * 0.22:
                    continue

                border_band = frame_mask[y:y + height, x:x + width]
                if border_band.size == 0 or float(np.mean(border_band > 0)) < 0.015:
                    continue

                regions.append(self._expand_bbox(
                    (x, y, x + width, y + height),
                    page_width,
                    page_height,
                    ratio=0.008,
                ))

            return regions
        except Exception as e:
            logger.warning(f"Frame-based region detection failed: {e}")
            return []

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
        inter = self._intersection_area(left, right)
        if inter == 0:
            return 0.0
        union = self._bbox_area(left) + self._bbox_area(right) - inter
        return inter / union if union > 0 else 0.0

    def _intersection_area(self, left: Tuple[int, int, int, int], right: Tuple[int, int, int, int]) -> int:
        lx0, ly0, lx1, ly1 = left
        rx0, ry0, rx1, ry1 = right
        ix0, iy0 = max(lx0, rx0), max(ly0, ry0)
        ix1, iy1 = min(lx1, rx1), min(ly1, ry1)
        return max(0, ix1 - ix0) * max(0, iy1 - iy0)

    def _contains(self, outer: Tuple[int, int, int, int], inner: Tuple[int, int, int, int]) -> bool:
        ox0, oy0, ox1, oy1 = outer
        ix0, iy0, ix1, iy1 = inner
        return ox0 <= ix0 and oy0 <= iy0 and ox1 >= ix1 and oy1 >= iy1

    def _is_hierarchical_overlap(
        self,
        left: Tuple[int, int, int, int],
        right: Tuple[int, int, int, int],
        min_area_ratio: float = 2.0,
    ) -> bool:
        """Return True when boxes are likely parent/child figures, not duplicates."""
        left_area = self._bbox_area(left)
        right_area = self._bbox_area(right)
        smaller_area = max(1, min(left_area, right_area))
        larger_area = max(left_area, right_area)
        if larger_area / smaller_area < min_area_ratio:
            return False

        overlap_of_smaller = self._intersection_area(left, right) / smaller_area
        return overlap_of_smaller >= 0.86

    def _contained_region_count(
        self,
        bbox: Tuple[int, int, int, int],
        regions: List[Tuple[int, int, int, int]],
        min_child_area_ratio: float = 0.035,
    ) -> int:
        area = self._bbox_area(bbox)
        count = 0
        for other in regions:
            if other == bbox:
                continue
            if not self._is_hierarchical_overlap(bbox, other):
                continue
            if self._bbox_area(other) < area and self._bbox_area(other) >= area * min_child_area_ratio:
                count += 1
        return count

    def _classify_region_hierarchy(
        self,
        bbox: Tuple[int, int, int, int],
        regions: List[Tuple[int, int, int, int]],
    ) -> str:
        if self._contained_region_count(bbox, regions) >= 2:
            return "composite_figure"

        bbox_area = self._bbox_area(bbox)
        for other in regions:
            if other == bbox or self._bbox_area(other) <= bbox_area:
                continue
            if self._is_hierarchical_overlap(other, bbox):
                return "sub_figure"

        return ""

    def _deduplicate_regions(
        self,
        regions: List[Tuple[int, int, int, int]],
        page_width: int,
        page_height: int,
    ) -> List[Tuple[int, int, int, int]]:
        candidates = [
            self._expand_bbox(raw_bbox, page_width, page_height)
            for raw_bbox in regions
        ]
        candidates = [
            bbox for bbox in candidates
            if self._bbox_area(bbox) >= 1200
        ]
        candidates.sort(key=lambda bbox: self._bbox_area(bbox), reverse=True)

        kept: List[Tuple[int, int, int, int]] = []
        for bbox in candidates:
            bbox_area = self._bbox_area(bbox)
            should_drop = False
            for kept_bbox in kept:
                kept_area = self._bbox_area(kept_bbox)
                smaller_area = max(1, min(bbox_area, kept_area))
                contained_ratio = self._intersection_area(
                    bbox, kept_bbox) / smaller_area
                if self._iou(bbox, kept_bbox) > 0.45 or contained_ratio > 0.80:
                    should_drop = True
                    break

            if not should_drop:
                kept.append(bbox)

        return kept

    def _region_gap(
        self,
        left: Tuple[int, int, int, int],
        right: Tuple[int, int, int, int],
    ) -> Tuple[int, int]:
        x_gap = max(0, max(left[0], right[0]) - min(left[2], right[2]))
        y_gap = max(0, max(left[1], right[1]) - min(left[3], right[3]))
        return x_gap, y_gap

    def _group_composite_figures(
        self,
        regions: List[Tuple[int, int, int, int]],
        page_width: int,
        page_height: int,
        margin_ratio: float = 0.22,
    ) -> List[Tuple[int, int, int, int]]:
        """Add synthetic parent boxes for nearby sub-figures while keeping children."""
        if len(regions) < 2:
            return regions

        margin_x = max(24, int(page_width * margin_ratio))
        margin_y = max(24, int(page_width * margin_ratio))
        visited = set()
        components: List[List[Tuple[int, int, int, int]]] = []

        for start_index, start_bbox in enumerate(regions):
            if start_index in visited:
                continue

            visited.add(start_index)
            component_indexes = [start_index]
            stack = [start_index]
            while stack:
                current_index = stack.pop()
                current_bbox = regions[current_index]
                for candidate_index, candidate_bbox in enumerate(regions):
                    if candidate_index in visited:
                        continue
                    x_gap, y_gap = self._region_gap(
                        current_bbox, candidate_bbox)
                    if x_gap <= margin_x and y_gap <= margin_y:
                        visited.add(candidate_index)
                        component_indexes.append(candidate_index)
                        stack.append(candidate_index)

            if len(component_indexes) >= 2:
                components.append([regions[index] for index in component_indexes])

        composite_regions: List[Tuple[int, int, int, int]] = []
        page_area = page_width * page_height
        for component in components:
            union_bbox = (
                min(bbox[0] for bbox in component),
                min(bbox[1] for bbox in component),
                max(bbox[2] for bbox in component),
                max(bbox[3] for bbox in component),
            )
            union_bbox = self._expand_bbox(
                union_bbox, page_width, page_height, ratio=0.025)
            union_area = self._bbox_area(union_bbox)
            if union_area > page_area * 0.75:
                continue

            largest_child_area = max(self._bbox_area(bbox)
                                     for bbox in component)
            if union_area < largest_child_area * 1.20:
                continue

            duplicate_parent = False
            for existing in regions + composite_regions:
                existing_area = self._bbox_area(existing)
                overlap_of_union = self._intersection_area(
                    union_bbox, existing) / max(1, union_area)
                if (
                    self._iou(union_bbox, existing) > 0.90
                    or (existing_area >= union_area * 0.90 and overlap_of_union > 0.95)
                ):
                    duplicate_parent = True
                    break

            if not duplicate_parent:
                composite_regions.append(union_bbox)

        grouped = composite_regions + regions
        grouped.sort(key=lambda bbox: self._bbox_area(bbox), reverse=True)
        return grouped

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
            overlap_children = 0

            for other in regions:
                if other == bbox:
                    continue
                overlap_ratio = self._iou(bbox, other)
                if overlap_ratio >= 0.18 and self._bbox_area(other) < area * 0.7:
                    overlap_children += 1

            is_wide_container = (
                width / max(1, page_width)) > 0.88 and (height / max(1, page_height)) < 0.26
            is_page_chrome = is_wide_container and (
                bbox[1] < page_height * 0.18 or bbox[3] > page_height * 0.92)
            if is_page_chrome and overlap_children >= 2:
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
            [(int(x0), int(y0), int(x1), int(y1))
             for x0, y0, x1, y1 in regions],
            key=lambda bbox: self._bbox_area(bbox),
            reverse=True,
        )
        selected: List[Tuple[int, int, int, int]] = []
        for bbox in ranked:
            if any(
                self._iou(bbox, kept) > 0.58
                and not self._is_hierarchical_overlap(bbox, kept)
                for kept in selected
            ):
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
            if area < 1200:
                continue
            if area > page_area * 0.75:
                continue

            edge_margin = int(min(page_width, page_height) * 0.012)
            if x0 <= edge_margin and y0 <= edge_margin and width < 170 and height < 170:
                continue

            refined.append(bbox)

        refined.sort(key=lambda item: self._bbox_area(item), reverse=True)
        deduped = self._deduplicate_regions(refined, page_width, page_height)
        return self._suppress_container_regions(deduped, page_width, page_height)

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
            images = convert_from_path(
                pdf_path,
                first_page=page_num + 1,
                last_page=page_num + 1,
                dpi=150,
                poppler_path=POPPLER_PATH,
            )
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

            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
            images = convert_from_path(
                pdf_path,
                first_page=page_num + 1,
                last_page=page_num + 1,
                dpi=150,
                poppler_path=POPPLER_PATH,
            )
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

            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
            text = pytesseract.image_to_string(image, lang="vie")
            return self._clean_text(text, max_chars=300)
        except Exception:
            return ""

    def _normalize_text(self, text: str) -> str:
        text = unicodedata.normalize("NFD", text.lower())
        text = "".join(
            char for char in text if unicodedata.category(char) != "Mn")
        return re.sub(r"[^a-z0-9\s]+", " ", text)

    def _clean_text(self, text: str, max_chars: int = 1200) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        return text[:max_chars]

    def _extract_section_title(self, page_text: str) -> str:
        """Find a compact lesson or section title from page OCR/PDF text."""
        lines = [line.strip()
                 for line in (page_text or "").splitlines() if line.strip()]
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
        lines = [line.strip()
                 for line in (page_text or "").splitlines() if line.strip()]
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

    def _infer_image_type(
        self,
        figure_label: str,
        context_text: str,
        crop_text: str = "",
        hierarchy_type: str = "",
    ) -> str:
        if hierarchy_type:
            return hierarchy_type

        normalized = self._normalize_text(f"{figure_label} {context_text}")
        crop_normalized = self._normalize_text(crop_text)
        crop_tokens = [token for token in crop_normalized.split()
                       if len(token) > 1]
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
    ) -> bool:
        """Reject standalone headings/labels that detector can mistake for figures."""
        normalized = self._normalize_text(crop_text)
        tokens = [token for token in normalized.split() if len(token) > 1]
        if len(tokens) <= 15:
            return False

        aspect_ratio = crop.width / crop.height if crop.height else 0
        crop_area = crop.width * crop.height
        image_keyword_pattern = (
            r"[\d=+\-*/^√≤≥<>]|"
            r"\b([a-d]\)|bang|hinh|anh|cong thuc|bieu do|so do|"
            r"thi nghiem|quan sat|mo hinh|vat mau|mau vat|"
            r"coc|nhiet ke|day|tuong|nhom|nen|the ran|the long)\b"
        )
        if re.search(image_keyword_pattern, normalized):
            return False

        visual_score = self._visual_content_score(crop)
        foreground_score = self._foreground_content_score(crop)
        has_visual_contrast = visual_score >= 0.035 or foreground_score >= 0.10
        if crop_area > 15000:
            return not has_visual_contrast and aspect_ratio < 9

        weak_visual = visual_score < 0.025 and foreground_score < 0.065
        return weak_visual and aspect_ratio < 9

    def _foreground_content_score(self, image: Image.Image) -> float:
        """Estimate non-white/non-background content so low-saturation objects survive."""
        img_array = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        foreground = gray < 238
        return float(np.mean(foreground))

    def _extract_keywords(self, *texts: str, limit: int = 18) -> str:
        """Extract lightweight Vietnamese keyword metadata without calling another model."""
        normalized = self._normalize_text(" ".join(texts))
        tokens = [token for token in normalized.split() if len(
            token) > 1 and token not in VIETNAMESE_STOPWORDS]

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

        hash_path = output_dir / \
            f"page_{page_num}_img_{img_index}_{img_hash[:8]}.png"
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
            candidate = output_dir / \
                f"page_{page_num}_img_{img_index}_{img_hash[:8]}_{attempt}.png"
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
        caption_text = metadata.get("caption_vi_manual", "") or metadata.get(
            "caption_vi", "") or metadata.get("caption", "")
        keywords_text = metadata.get(
            "keywords_vi_manual", "") or metadata.get("keywords_vi", "")
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

        Phase 1: OWL-ViT open-vocabulary object detection for region discovery
        Phase 2: Region refinement, dedupe, and caps
        Phase 3: Vietnamese OCR/context metadata + storage
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
            page_snapshot_path = self._save_page_snapshot(
                output_dir, page_num, pil_img)

            # Phase 1: OWL-ViT open-vocabulary detection for region discovery.
            logger.info(
                f"[Phase 1][page={page_num}] Detecting candidate image regions with OWL-ViT")
            owlvit_regions = self._detect_regions_with_owlvit(
                pil_img, OWL_VIT_TEXT_QUERIES)
            framed_regions = self._detect_framed_regions(img_array)
            regions = owlvit_regions + framed_regions

            # Phase 2: Refinement with aspect ratio, dedupe, and region caps.
            logger.info(
                f"[Phase 2][page={page_num}] Refining {len(owlvit_regions)} OWL-ViT and {len(framed_regions)} framed regions")
            refined = self._refine_regions(regions, img_array)
            refined = self._group_composite_figures(
                refined, pil_img.width, pil_img.height)
            refined = self._limit_regions_for_extraction(
                refined, max_regions=24)

            logger.debug(
                f"Page {page_num}: detected {len(regions)} regions, {len(refined)} after refinement")

            img_index = 0
            page_seen_hashes = set()
            for bbox in refined:
                x0, y0, x1, y1 = bbox
                crop = pil_img.crop((x0, y0, x1, y1))

                if crop.width < 50 or crop.height < 50:
                    continue

                # Phase 3: Vietnamese OCR/context metadata and storage.
                logger.info(
                    f"[Phase 3][page={page_num}][candidate={img_index}] Building OCR/context metadata")
                crop_text = self._ocr_crop_text(crop)
                if self._is_text_dominant_crop(crop, crop_text):
                    logger.debug(
                        f"Page {page_num} img {img_index}: filtered out as text-dominant crop")
                    img_index += 1
                    continue

                img_bytes = io.BytesIO()
                crop.save(img_bytes, format="PNG")
                img_bytes.seek(0)
                img_data = img_bytes.read()

                img_hash = self._compute_image_hash(img_data)
                if img_hash in page_seen_hashes:
                    logger.debug(
                        f"Page {page_num} img {img_index}: duplicate hash, skipping")
                    img_index += 1
                    continue
                page_seen_hashes.add(img_hash)

                image_id = self._build_image_id(
                    pdf_hash, page_num, bbox, img_hash)

                filepath = self._resolve_image_path(
                    output_dir, page_num, img_index, img_hash)

                with open(filepath, "wb") as f:
                    f.write(img_data)

                context_text = self._get_context_text(
                    pdf_path, page_num, bbox, page_text)
                context_text = self._clean_text(context_text, max_chars=1200)
                local_text = "\n".join(part for part in (
                    context_text, crop_text) if part)
                figure_label = self._extract_figure_label(local_text, "")
                figure_caption = self._extract_figure_caption(local_text, "")
                hierarchy_type = self._classify_region_hierarchy(bbox, refined)
                image_type = self._infer_image_type(
                    figure_label, context_text, crop_text, hierarchy_type)
                caption_context = {
                    "pdf_filename": pdf_filename,
                    "page_number": page_num,
                    "lesson_title": lesson_title,
                    "section_title": section_title,
                    "figure_label": figure_label,
                    "figure_caption": figure_caption,
                    "image_type": image_type,
                    "region_hierarchy": hierarchy_type or "standalone",
                    "context_text": context_text,
                    "crop_text": crop_text,
                    "nearby_text": nearby_text,
                }
                visual_metadata = self.captioner.caption(
                    crop, img_hash, context=caption_context)
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
                    "region_hierarchy": hierarchy_type or "standalone",
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
                    "clip_positive_score": 0.0,
                    "clip_negative_score": 0.0,
                    "detector_model": OWL_VIT_MODEL,
                    "detector_threshold": OWL_VIT_CONFIDENCE_THRESHOLD,
                }
                search_text = self._build_image_search_text(metadata)
                metadata["search_text"] = search_text

                doc = Document(page_content=search_text, metadata=metadata)
                extracted_docs.append(doc)
                self._append_review_manifest(metadata)

                logger.debug(
                    f"Saved: {filepath} (label={figure_label or image_type}, keywords={keywords_vi[:80]})")
                img_index += 1

            self.status_tracker.mark_image_extracted(
                pdf_hash,
                page_num,
                pdf_filename,
                image_extraction_version=self.image_extraction_version,
            )

        logger.info(
            f"[{pdf_filename}] Extracted {len(extracted_docs)} images from {total_pages} pages")
        return extracted_docs
