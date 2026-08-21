"""Caption ảnh (Vintern-1B / InternVL) cho các crop hình trong SGK.

TRẠNG THÁI: đường code ở đây ĐÃ CHẠY ĐƯỢC, nhưng tính năng **tắt theo mặc định**
(`IMAGE_CAPTION_ENABLED=false`) vì đã đo là không dùng được — xem D-47.

Lịch sử: D-42 phát hiện `_load_model` gọi `AutoModelForImageTextToText`, trong khi
Vintern-1B là **InternVL** (đăng ký qua `AutoModel` + remote code), nên
transformers 4.46.3 raise và một `except` nuốt lỗi rồi đặt `self.enabled = False`
— fallback im lặng: `IMAGE_CAPTION_ENABLED=true` mà mọi hình vẫn không có caption.
Nay đã sửa: `AutoModel` + `AutoTokenizer`, tiền xử lý dynamic-patch của InternVL,
và `_chat`/`_generate_ids` thay cho `.chat()` (remote code ghim `.cuda()` và
truyền `return_dict` gây TypeError). Không còn `except` nào nuốt lỗi.

Đo trên 12 crop thật (4 quyển, CPU, float32, max_patches=6, 100 token):
- 17,6 s/crop (min 3,8 — max 27,9) → ~4,8 h cho ~976 crop toàn corpus;
- JSON parse được 6/12 với prompt JSON, 0/12 với prompt văn xuôi;
- 4/12 caption BỊA chi tiết không có trong ảnh (crop "giác mút treo" thành
  "phẫu thuật viên ... mổ tai lưỡi"; đập thuỷ điện thành "ngọn hải đăng");
- **0/4 số hiệu hình do model tự nêu là đúng** (1.1→1.3, 2.2→2.1, 16.11→16.3);
- phần duy nhất đáng tin là chữ nó OCR lại từ chính crop, mà đó là dữ liệu
  pipeline đã có deterministic (`layout/pill.py` + caption anchor, D-45).

Với sách giáo khoa, một caption bịa tệ hơn không có caption (nguyên tắc 1), nên
mặc định là TẮT. Bật lại đòi phép đo mới, không phải trực giác.
"""

from __future__ import annotations

import hashlib
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
    IMAGE_CAPTION_MAX_PATCHES,
    IMAGE_CAPTION_MODEL,
    USE_GPU,
)

logger = logging.getLogger(__name__)


CAPTION_CONTEXT_VERSION = "context_v1"

# --- Tiền xử lý ảnh của InternVL ---------------------------------------------
# Vintern-1B là một InternVL model: nó KHÔNG dùng AutoProcessor. Ảnh phải được
# cắt thành các ô 448x448 theo tỉ lệ khung gần nhất ("dynamic patches") cộng một
# thumbnail, rồi normalize theo ImageNet. Công thức dưới đây lấy đúng từ
# `models/Vintern-1B-v2/README.md` (mục Quickstart) — không tự sáng tác, vì lệch
# một bước normalize là ảnh vào model sai và caption sẽ bịa.
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
INTERNVL_TILE_SIZE = 448


def _build_transform(input_size: int):
    import torchvision.transforms as T
    from torchvision.transforms.functional import InterpolationMode

    return T.Compose([
        T.Lambda(lambda img: img.convert("RGB")
                 if img.mode != "RGB" else img),
        T.Resize((input_size, input_size),
                 interpolation=InterpolationMode.BICUBIC),
        T.ToTensor(),
        T.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
    ])


def _find_closest_aspect_ratio(aspect_ratio, target_ratios, width, height, image_size):
    best_ratio_diff = float("inf")
    best_ratio = (1, 1)
    area = width * height
    for ratio in target_ratios:
        target_aspect_ratio = ratio[0] / ratio[1]
        ratio_diff = abs(aspect_ratio - target_aspect_ratio)
        if ratio_diff < best_ratio_diff:
            best_ratio_diff = ratio_diff
            best_ratio = ratio
        elif ratio_diff == best_ratio_diff:
            if area > 0.5 * image_size * image_size * ratio[0] * ratio[1]:
                best_ratio = ratio
    return best_ratio


def _dynamic_preprocess(
    image: Image.Image,
    min_num: int = 1,
    max_num: int = 6,
    image_size: int = INTERNVL_TILE_SIZE,
    use_thumbnail: bool = True,
) -> List[Image.Image]:
    orig_width, orig_height = image.size
    aspect_ratio = orig_width / max(orig_height, 1)

    target_ratios = sorted(
        {
            (i, j)
            for n in range(min_num, max_num + 1)
            for i in range(1, n + 1)
            for j in range(1, n + 1)
            if min_num <= i * j <= max_num
        },
        key=lambda x: x[0] * x[1],
    )
    target_aspect_ratio = _find_closest_aspect_ratio(
        aspect_ratio, target_ratios, orig_width, orig_height, image_size)

    target_width = image_size * target_aspect_ratio[0]
    target_height = image_size * target_aspect_ratio[1]
    blocks = target_aspect_ratio[0] * target_aspect_ratio[1]

    resized_img = image.resize((target_width, target_height))
    processed_images = []
    for i in range(blocks):
        box = (
            (i % (target_width // image_size)) * image_size,
            (i // (target_width // image_size)) * image_size,
            ((i % (target_width // image_size)) + 1) * image_size,
            ((i // (target_width // image_size)) + 1) * image_size,
        )
        processed_images.append(resized_img.crop(box))

    if use_thumbnail and len(processed_images) != 1:
        processed_images.append(image.resize((image_size, image_size)))
    return processed_images

BASE_CAPTION_PROMPT = (
    "Bạn là bộ tạo metadata ảnh cho hệ thống tìm kiếm sách giáo khoa sinh học. "
    "Hãy mô tả ảnh bằng tiếng Việt, ưu tiên giúp truy vấn tìm được đúng ảnh. "
    "Dựa vào ảnh để nhận diện vật thể chính, loài sinh vật, bộ phận cơ thể, môi trường, màu sắc hoặc hoạt động. "
    "Dùng thêm ngữ cảnh OCR/metadata nếu nó làm rõ chủ đề, môi trường hoặc nhãn hình. "
    "Ví dụ: nếu ảnh có cá/rạn san hô và ngữ cảnh ghi 'Đại dương', hãy đưa 'đại dương' vào caption/keywords/scene. "
    "Không bịa tên loài hoặc chi tiết không thấy rõ. "
    "Trả về đúng JSON với các khóa: caption, keywords, objects, scene. "
    'Ví dụ: {"caption":"các loài cá bơi trong đại dương gần rạn san hô",'
    '"keywords":["cá","đại dương","rạn san hô"],"objects":["cá","san hô"],"scene":"đại dương"}.'
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
        self._tokenizer = None
        self._model = None
        self._device = "cuda" if USE_GPU and torch.cuda.is_available() else "cpu"
        # bfloat16 theo README chỉ dành cho GPU; trên CPU không có kernel
        # bf16 tương ứng nên dùng float32.
        self._dtype = torch.bfloat16 if self._device == "cuda" else torch.float32
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
        """Nạp Vintern-1B (InternVL) — RAISE nếu thất bại, không nuốt lỗi.

        Trước đây hàm này bắt mọi Exception, log `warning`, rồi đặt
        `self.enabled = False`. Hệ quả: `IMAGE_CAPTION_ENABLED=true` mà mọi hình
        vẫn được index KHÔNG có caption — đúng loại fallback im lặng mà nguyên
        tắc 5 cấm (D-42). Nay: bật mà hỏng thì ETL dừng ồn ào; không muốn caption
        thì đặt `IMAGE_CAPTION_ENABLED=false`.
        """
        if not self.enabled:
            return False
        if self._model is not None and self._tokenizer is not None:
            return True

        # Vintern-1B = InternVL2-1B: đăng ký qua AutoModel + remote code, KHÔNG
        # qua AutoModelForImageTextToText (transformers 4.46.3 raise
        # "Unrecognized configuration class InternVLChatConfig"), và KHÔNG có
        # AutoProcessor — chỉ AutoTokenizer + tiền xử lý ảnh riêng ở trên.
        from transformers import AutoModel, AutoTokenizer

        logger.info(f"Loading image caption model: {self.model_name}")
        token = HF_TOKEN if HF_TOKEN else None
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_name,
            token=token,
            trust_remote_code=True,
            use_fast=False,
        )
        self._model = AutoModel.from_pretrained(
            self.model_name,
            token=token,
            trust_remote_code=True,
            torch_dtype=self._dtype,
            low_cpu_mem_usage=True,
        ).eval()
        self._model.to(self._device)
        logger.info(
            f"Image caption model loaded ({self._device}/{self._dtype}, "
            f"max_patches={IMAGE_CAPTION_MAX_PATCHES})")
        return True

    def _cache_key(self, image_hash: str, context: Optional[Dict[str, Any]] = None) -> str:
        context_payload = self._normalize_context(context)
        if not context_payload:
            return f"{self.model_name}:{CAPTION_CONTEXT_VERSION}:{image_hash}"

        fingerprint = hashlib.sha1(
            json.dumps(context_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return f"{self.model_name}:{CAPTION_CONTEXT_VERSION}:{image_hash}:{fingerprint}"

    def caption(
        self,
        image: Image.Image,
        image_hash: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return cached or generated visual metadata for one image crop."""
        empty = {
            "visual_caption_vi": "",
            "visual_keywords_vi": "",
            "visual_objects_vi": "",
            "visual_scene_vi": "",
            "caption_source": "none",
            "caption_context_used": "",
        }
        if not self.enabled:
            return empty

        context_payload = self._normalize_context(context)
        cache_key = self._cache_key(image_hash, context_payload)
        if cache_key in self._cache:
            return dict(self._cache[cache_key])

        if not self._load_model():
            return empty

        # Không bọc try/except: một crop caption lỗi phải làm cả TRANG đó thất
        # bại và được để lại chưa xử lý (main.py bỏ qua & thử lại lần sau), chứ
        # không được ghi vào index một nửa dữ liệu (nguyên tắc 5).
        raw_text = self._generate_caption(image, context_payload)
        parsed = self._parse_caption(raw_text)
        parsed["caption_context_used"] = "yes" if context_payload else "no"
        self._cache[cache_key] = parsed
        self._save_cache()
        return dict(parsed)

    def _preprocess_image(self, image: Image.Image) -> "torch.Tensor":
        tiles = _dynamic_preprocess(
            image.convert("RGB"),
            max_num=max(1, IMAGE_CAPTION_MAX_PATCHES),
            image_size=INTERNVL_TILE_SIZE,
            use_thumbnail=True,
        )
        transform = _build_transform(INTERNVL_TILE_SIZE)
        pixel_values = torch.stack([transform(tile) for tile in tiles])
        return pixel_values.to(self._dtype).to(self._device)

    def _generate_caption(self, image: Image.Image, context: Optional[Dict[str, Any]] = None) -> str:
        """Sinh caption qua API `.chat()` của InternVL.

        Bản cũ dựng `messages` + `processor(...)` + `model.generate(**inputs)` —
        sai API: InternVLChatModel.generate nhận `pixel_values` + `input_ids` đã
        có đủ token <IMG_CONTEXT>, việc chèn token đó nằm trong `.chat()`.
        """
        pixel_values = self._preprocess_image(image)
        question = "<image>\n" + self._build_prompt(context)
        generation_config = {
            "max_new_tokens": IMAGE_CAPTION_MAX_NEW_TOKENS,
            "do_sample": False,
            "num_beams": 1,
            "repetition_penalty": 2.5,
        }
        with torch.no_grad():
            return self._chat(pixel_values, question, generation_config)

    def _chat(self, pixel_values, question: str, generation_config: Dict[str, Any]) -> str:
        """Bản `.chat()` của InternVL nhưng KHÔNG ghim `.cuda()`.

        `modeling_internvl_chat.py::chat` gọi thẳng `input_ids.cuda()`, nên trên
        máy `torch 2.11.0+cpu` nó raise "Torch not compiled with CUDA enabled".
        Ở đây lặp lại đúng các bước của nó (conv template → chèn
        `<IMG_CONTEXT>` × num_image_token × num_patches → generate → cắt ở
        `template.sep`) và đặt tensor lên `self._device`.
        """
        import importlib

        remote = importlib.import_module(type(self._model).__module__)
        tokenizer = self._tokenizer
        img_start, img_end, img_ctx = "<img>", "</img>", "<IMG_CONTEXT>"

        self._model.img_context_token_id = tokenizer.convert_tokens_to_ids(
            img_ctx)

        template = remote.get_conv_template(self._model.template)
        template.system_message = self._model.system_message
        eos_token_id = tokenizer.convert_tokens_to_ids(template.sep)
        template.append_message(template.roles[0], question)
        template.append_message(template.roles[1], None)
        query = template.get_prompt()

        num_patches = pixel_values.shape[0]
        image_tokens = (
            img_start
            + img_ctx * self._model.num_image_token * num_patches
            + img_end
        )
        query = query.replace("<image>", image_tokens, 1)

        model_inputs = tokenizer(query, return_tensors="pt")
        input_ids = model_inputs["input_ids"].to(self._device)
        attention_mask = model_inputs["attention_mask"].to(self._device)

        config = dict(generation_config)
        config["eos_token_id"] = eos_token_id
        output = self._generate_ids(
            pixel_values, input_ids, attention_mask, config)
        response = tokenizer.batch_decode(output, skip_special_tokens=True)[0]
        return response.split(template.sep)[0].strip()

    def _generate_ids(self, pixel_values, input_ids, attention_mask, config):
        """Chèn embedding ảnh vào chỗ token <IMG_CONTEXT> rồi generate.

        Không gọi được `InternVLChatModel.generate` của remote code: nó truyền
        `return_dict=None` xuống `language_model.generate`, transformers 4.46.3
        đưa kwarg lạ đó vào `model_kwargs` rồi gọi `forward(..., return_dict=True)`
        -> `TypeError: got multiple values for keyword argument 'return_dict'`.
        Các bước dưới đây sao đúng phần thân của nó, bỏ tham số gây lỗi.
        """
        model = self._model
        vit_embeds = model.extract_feature(pixel_values)
        input_embeds = model.language_model.get_input_embeddings()(input_ids)
        batch, length, channels = input_embeds.shape
        input_embeds = input_embeds.reshape(batch * length, channels)

        flat_ids = input_ids.reshape(batch * length)
        selected = flat_ids == model.img_context_token_id
        # Số ô ảnh phải khớp đúng số token <IMG_CONTEXT> đã chèn; lệch là lỗi
        # lập trình, không phải dữ liệu, nên để nó nổ.
        assert int(selected.sum()) == vit_embeds.reshape(-1, channels).shape[0]
        input_embeds[selected] = vit_embeds.reshape(
            -1, channels).to(input_embeds.device)
        input_embeds = input_embeds.reshape(batch, length, channels)

        return model.language_model.generate(
            inputs_embeds=input_embeds,
            attention_mask=attention_mask,
            use_cache=True,
            **config,
        )

    def _build_prompt(self, context: Optional[Dict[str, Any]] = None) -> str:
        context_payload = self._normalize_context(context)
        if not context_payload:
            return BASE_CAPTION_PROMPT

        lines = ["Ngữ cảnh trang/crop:"]
        labels = {
            "pdf_filename": "Tài liệu",
            "page_number": "Trang",
            "lesson_title": "Bài/chủ đề",
            "section_title": "Mục",
            "figure_label": "Nhãn hình",
            "figure_caption": "Chú thích hình",
            "image_type": "Loại ảnh",
            "context_text": "OCR quanh ảnh",
            "crop_text": "OCR trong crop",
            "nearby_text": "OCR toàn trang",
        }
        for key, label in labels.items():
            value = context_payload.get(key, "")
            if value:
                lines.append(f"- {label}: {value}")

        return BASE_CAPTION_PROMPT + "\n\n" + "\n".join(lines)

    def _normalize_context(self, context: Optional[Dict[str, Any]]) -> Dict[str, str]:
        if not context:
            return {}

        limits = {
            "pdf_filename": 120,
            "page_number": 20,
            "lesson_title": 180,
            "section_title": 180,
            "figure_label": 120,
            "figure_caption": 260,
            "image_type": 80,
            "context_text": 700,
            "crop_text": 260,
            "nearby_text": 700,
        }
        normalized: Dict[str, str] = {}
        for key, max_chars in limits.items():
            value = self._clean_text(context.get(key, ""), max_chars=max_chars)
            if value:
                normalized[key] = value
        return normalized

    def _parse_caption(self, raw_text: str) -> Dict[str, Any]:
        payload = self._extract_json(raw_text) or {}
        caption = self._clean_text(payload.get(
            "caption") or raw_text, max_chars=240)
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
            "caption_context_used": "no",
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
        stopwords = {"hinh", "anh", "mot", "tren",
                     "trong", "cac", "voi", "cua", "va", "co"}
        normalized = caption.lower()
        normalized = re.sub(r"[^a-zA-Z0-9À-ỹ\s]+", " ", normalized)
        return [
            token
            for token in normalized.split()
            if len(token) > 1 and token not in stopwords
        ][:12]
