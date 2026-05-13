"""Vision-language captioning for extracted textbook images."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from PIL import Image

from ..config import (
    HF_TOKEN,
    IMAGE_CAPTION_CACHE_PATH,
    IMAGE_CAPTION_ENABLED,
    IMAGE_CAPTION_MAX_NEW_TOKENS,
    IMAGE_CAPTION_MODEL,
    USE_GPU,
)

logger = logging.getLogger(__name__)


CAPTION_PROMPT = (
    "Mô tả ngắn gọn bằng tiếng Việt hình ảnh này cho hệ thống tìm kiếm sách giáo khoa sinh học. "
    "Tập trung vào vật thể chính, loài sinh vật, bộ phận cơ thể, môi trường, màu sắc hoặc hoạt động nếu nhìn thấy. "
    "Không đoán quá xa ngoài hình. Trả về đúng JSON với các khóa: "
    'caption, keywords, objects, scene. Ví dụ: {"caption":"hình một con trâu trên bãi cỏ",'
    '"keywords":["trâu","động vật","bãi cỏ"],"objects":["trâu"],"scene":"đồng cỏ"}.'
)


class ImageCaptioner:
    """Lazy, cached Vietnamese image captioner."""

    def __init__(
        self,
        model_name: str = IMAGE_CAPTION_MODEL,
        enabled: bool = IMAGE_CAPTION_ENABLED,
        cache_path: Path = IMAGE_CAPTION_CACHE_PATH,
    ):
        self.model_name = model_name
        self.enabled = enabled
        self.cache_path = Path(cache_path)
        self._processor = None
        self._model = None
        self._device = "cuda" if USE_GPU and torch.cuda.is_available() else "cpu"
        self._cache: Dict[str, Dict[str, Any]] = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Could not load image caption cache: {e}")
            return {}

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Could not save image caption cache: {e}")

    def _load_model(self) -> bool:
        if not self.enabled:
            return False
        if self._model is not None and self._processor is not None:
            return True

        try:
            from transformers import AutoProcessor

            try:
                from transformers import AutoModelForImageTextToText as CaptionModel
            except ImportError:
                from transformers import AutoModelForVision2Seq as CaptionModel

            logger.info(f"Loading image caption model: {self.model_name}")
            self._processor = AutoProcessor.from_pretrained(
                self.model_name,
                token=HF_TOKEN if HF_TOKEN else None,
                trust_remote_code=True,
            )

            model_kwargs = {
                "token": HF_TOKEN if HF_TOKEN else None,
                "trust_remote_code": True,
            }
            if self._device == "cuda":
                model_kwargs.update({"torch_dtype": torch.float16, "device_map": "auto"})

            self._model = CaptionModel.from_pretrained(self.model_name, **model_kwargs)
            if self._device != "cuda":
                self._model.to(self._device)
            self._model.eval()
            logger.info("Image caption model loaded")
            return True
        except Exception as e:
            logger.warning(f"Image caption model unavailable, continuing without visual captions: {e}")
            self.enabled = False
            return False

    def _cache_key(self, image_hash: str) -> str:
        return f"{self.model_name}:{image_hash}"

    def caption(self, image: Image.Image, image_hash: str) -> Dict[str, Any]:
        """Return cached or generated visual metadata for one image crop."""
        empty = {
            "visual_caption_vi": "",
            "visual_keywords_vi": "",
            "visual_objects_vi": "",
            "visual_scene_vi": "",
            "caption_source": "none",
        }
        if not self.enabled:
            return empty

        cache_key = self._cache_key(image_hash)
        if cache_key in self._cache:
            return dict(self._cache[cache_key])

        if not self._load_model():
            return empty

        try:
            raw_text = self._generate_caption(image)
            parsed = self._parse_caption(raw_text)
            self._cache[cache_key] = parsed
            self._save_cache()
            return dict(parsed)
        except Exception as e:
            logger.warning(f"Image captioning failed: {e}")
            return empty

    def _generate_caption(self, image: Image.Image) -> str:
        if hasattr(self._processor, "apply_chat_template"):
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image.convert("RGB")},
                        {"type": "text", "text": CAPTION_PROMPT},
                    ],
                }
            ]
            prompt = self._processor.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            prompt = CAPTION_PROMPT

        inputs = self._processor(
            text=[prompt],
            images=[image.convert("RGB")],
            return_tensors="pt",
            padding=True,
        )
        inputs = {
            key: value.to(self._model.device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }

        with torch.no_grad():
            generated_ids = self._model.generate(
                **inputs,
                max_new_tokens=IMAGE_CAPTION_MAX_NEW_TOKENS,
                do_sample=False,
            )

        input_len = inputs["input_ids"].shape[-1] if "input_ids" in inputs else 0
        if input_len and generated_ids.shape[-1] > input_len:
            generated_ids = generated_ids[:, input_len:]
        return self._processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()

    def _parse_caption(self, raw_text: str) -> Dict[str, Any]:
        payload = self._extract_json(raw_text) or {}
        caption = self._clean_text(payload.get("caption") or raw_text, max_chars=240)
        keywords = self._clean_list(payload.get("keywords"))
        objects = self._clean_list(payload.get("objects"))
        scene = self._clean_text(payload.get("scene") or "", max_chars=120)

        if not keywords:
            keywords = self._fallback_keywords(caption)

        return {
            "visual_caption_vi": caption,
            "visual_keywords_vi": ", ".join(keywords[:12]),
            "visual_objects_vi": ", ".join(objects[:8]),
            "visual_scene_vi": scene,
            "caption_source": self.model_name,
        }

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _clean_text(self, text: Any, max_chars: int) -> str:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        return cleaned[:max_chars]

    def _clean_list(self, value: Any) -> List[str]:
        if isinstance(value, str):
            items = re.split(r"[,;\n]+", value)
        elif isinstance(value, list):
            items = value
        else:
            items = []

        cleaned = []
        seen = set()
        for item in items:
            text = self._clean_text(item, max_chars=40).lower()
            if text and text not in seen:
                cleaned.append(text)
                seen.add(text)
        return cleaned

    def _fallback_keywords(self, caption: str) -> List[str]:
        stopwords = {"hinh", "anh", "mot", "tren", "trong", "cac", "voi", "cua", "va", "co"}
        normalized = caption.lower()
        normalized = re.sub(r"[^a-zA-Z0-9À-ỹ\s]+", " ", normalized)
        return [
            token
            for token in normalized.split()
            if len(token) > 1 and token not in stopwords
        ][:12]
