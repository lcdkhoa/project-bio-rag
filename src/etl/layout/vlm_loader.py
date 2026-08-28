# -*- coding: utf-8 -*-
"""Nạp VLM bằng auto-class đúng và kiểm tra tie-weights (D-99/D-101).

Chuyển từ `scripts/colab_run_ocr_engines.py` sang production để dùng chung giữa
bake-off và `FormulaMinerUClient` (`formula_ocr.py`).
"""
from __future__ import annotations

# Thứ tự thử auto-class. **ĐO ĐƯỢC, không phải phỏng đoán** — đọc `config.json`
# trên HF (2026-08-26):
#     nanonets/Nanonets-OCR2-3B          arch Qwen2_5_VLForConditionalGeneration, auto_map RỖNG
#     opendatalab/MinerU2.5-Pro-...      arch Qwen2VLForConditionalGeneration,   auto_map RỖNG
#     dots-studio/dots.ocr               arch DotsOCRForCausalLM, auto_map = {AutoConfig, AutoModelForCausalLM}
# Nghĩa là bản cũ dùng MỘT `AutoModelForCausalLM` cho cả ba sẽ chết ở 2/3 engine
# ngay bước nạp model: `qwen2_vl`/`qwen2_5_vl` không nằm trong registry của
# AutoModelForCausalLM, chúng nằm ở MODEL_FOR_IMAGE_TEXT_TO_TEXT_MAPPING.
_AUTO_CLASSES = ("AutoModelForImageTextToText", "AutoModelForCausalLM",
                 "AutoModelForVision2Seq")


def _tie_da_xay_ra(model) -> bool:
    """lm_head có dùng CHUNG bộ nhớ với bảng embedding không.

    Dùng `get_input_embeddings` / `get_output_embeddings` (API chuẩn) chứ không
    dò tên thuộc tính, vì mỗi họ VLM đặt tên một kiểu.
    """
    lay_out = getattr(model, "get_output_embeddings", None)
    lay_inp = getattr(model, "get_input_embeddings", None)
    if lay_out is None or lay_inp is None:
        print("[cổng tie] model không có get_(in|out)put_embeddings -> KHÔNG "
              "kiểm được lm_head. Đọc kỹ vài ô đầu bằng --doi-chieu.", flush=True)
        return True
    out = lay_out()
    inp = lay_inp()
    if out is None:
        # KHÔNG phải bằng chứng model ổn: nhiều VLM giấu lm_head dưới
        # `model.language_model`, nên `get_output_embeddings()` trả None trong
        # khi lm_head vẫn có thật và vẫn có thể chưa được buộc. Cổng im lặng ở
        # đây là đúng cái bệnh nó sinh ra để chặn.
        thu = _lm_head_sau(model)
        if thu is None:
            print("[cổng tie] get_output_embeddings() = None và không tìm thấy "
                  "lm_head ở lớp sâu -> coi như model không có lm_head riêng.",
                  flush=True)
            return True
        out = thu
        print("[cổng tie] get_output_embeddings() = None nhưng TÌM THẤY lm_head "
              "ở lớp sâu -> vẫn kiểm.", flush=True)
    if inp is None:
        print("[cổng tie] get_input_embeddings() = None -> không có gì để so.",
              flush=True)
        return False
    ok = out.weight.data_ptr() == inp.weight.data_ptr()
    print(f"[cổng tie] lm_head {'ĐÃ' if ok else 'CHƯA'} buộc với embedding "
          f"(ptr {out.weight.data_ptr()} vs {inp.weight.data_ptr()})", flush=True)
    return ok


def _lm_head_sau(model):
    """Tìm `lm_head` ở các lớp sâu khi `get_output_embeddings()` trả None.

    Qwen2.5-VL trong transformers 5.x đặt phần ngôn ngữ dưới
    `model.language_model`, nên lớp ngoài có thể không lộ lm_head ra.
    """
    for duong in ("lm_head", "language_model.lm_head",
                  "model.lm_head", "model.language_model.lm_head"):
        obj = model
        for phan in duong.split("."):
            obj = getattr(obj, phan, None)
            if obj is None:
                break
        if obj is not None and getattr(obj, "weight", None) is not None:
            return obj
    return None


def _khai_bao_tie(model_id: str) -> bool:
    """`tie_word_embeddings` model TỰ KHAI — top-level, rồi tới `text_config`.

    Nanonets-OCR2-3B khai nó **chỉ trong `text_config`** (top-level là `None`),
    và `model.safetensors.index.json` **không có key `lm_head.weight`** nào
    trong 824 key — tức checkpoint thật sự tied.
    """
    from transformers import AutoConfig

    cfg = AutoConfig.from_pretrained(model_id, trust_remote_code=True)
    for obj in (cfg, getattr(cfg, "text_config", None)):
        v = getattr(obj, "tie_word_embeddings", None) if obj is not None else None
        if v is not None:
            return bool(v)
    return False


def _load_vlm(model_id: str, torch, fn_khai_bao_tie=None, fn_tie_da_xay_ra=None):
    """Nạp VLM bằng auto-class ĐÚNG cho model đó, và NÓI RA dùng class nào.

    Không thử-rồi-nuốt: mọi lỗi được giữ lại, và nếu không class nào nạp được thì
    raise kèm ĐỦ danh sách lỗi. Một fallback im lặng ở đây sẽ khiến engine chạy
    bằng đường không ai kiểm — đúng bệnh đã cắn năm lần (D-68, D-75, D-83, D-84, D-94).
    """
    import transformers

    check_tie = fn_tie_da_xay_ra or _tie_da_xay_ra
    check_khai_bao = fn_khai_bao_tie or _khai_bao_tie

    # `torch_dtype` bị bỏ ở transformers 5.x, `dtype` chỉ có từ 4.56. Chọn theo
    # phiên bản THẬT trên Colab thay vì đoán.
    major = int(str(transformers.__version__).split(".")[0])
    dtype_kw = ({"dtype": torch.bfloat16} if major >= 5
                else {"torch_dtype": torch.bfloat16})

    # CẢNH BÁO SỚM: transformers 5.x nạp hỏng lm_head của Nanonets (D-101)
    if transformers.__version__.startswith("5."):
        print("[CẢNH BÁO] Bạn đang dùng transformers "
              f"{transformers.__version__} (5.x). Phiên bản này ĐÃ ĐO ĐƯỢC "
              "là nạp hỏng lm_head của Nanonets-OCR2-3B (model sinh RÁC, không "
              "phải đọc kém).", flush=True)
        print("!! Nếu chữ đọc ra là token ngẫu nhiên: "
              "`pip install -U 'transformers>=4.49,<5'` rồi Runtime -> Restart.",
              flush=True)

    loi = []
    for ten in _AUTO_CLASSES:
        cls = getattr(transformers, ten, None)
        if cls is None:
            loi.append(f"{ten}: transformers {transformers.__version__} không có class này")
            continue
        try:
            model = cls.from_pretrained(model_id, trust_remote_code=True,
                                        device_map="auto", **dtype_kw)
        except Exception as exc:  # noqa: BLE001 — gom lại rồi raise, không nuốt
            loi.append(f"{ten}: {type(exc).__name__}: {exc}")
            continue
        print(f"[nạp] {model_id} <- transformers.{ten} "
              f"(transformers {transformers.__version__})", flush=True)

        # CỔNG: model nạp THIẾU TRỌNG SỐ mà vẫn sinh chữ là fallback im lặng tệ
        # nhất trong cả repo này — nó sinh RÁC trông y hệt "engine đọc kém", nên
        # bảng sẽ ghi CT 0,000 và ta loại oan một model có thể tốt.
        #
        # Ca thật (2026-08-26, Colab, transformers 5.15.1): Nanonets-OCR2-3B báo
        # `lm_head.weight | MISSING` rồi đọc 3/3 ô ra token ngẫu nhiên đa ngôn
        # ngữ. ĐO ĐƯỢC nguyên nhân: `model.safetensors.index.json` không có key
        # `lm_head.weight` nào trong 824 key (checkpoint TIED), và
        # `tie_word_embeddings: true` chỉ khai trong `text_config` — top-level là
        # `None`. transformers 5.x không buộc trọng số, lm_head thành ngẫu nhiên.
        if not check_tie(model) and check_khai_bao(model_id):
            print("[vá] lm_head CHƯA được buộc với embedding dù model khai "
                  "tie_word_embeddings=True -> gọi tie_weights()", flush=True)
            model.tie_weights()
            if not check_tie(model):
                raise RuntimeError(
                    f"{model_id}: lm_head vẫn KHÔNG được buộc sau tie_weights() "
                    f"trên transformers {transformers.__version__}. Model sẽ sinh "
                    "RÁC chứ không phải đọc kém — dừng ở đây thay vì để nó chấm "
                    "một bảng vô nghĩa. Thử `pip install 'transformers<5'`.")
            print("[vá] xong: lm_head và embedding nay dùng chung trọng số.",
                  flush=True)
        return model

    raise RuntimeError(
        f"Không auto-class nào nạp được {model_id!r}. Đã thử:" + "\n  "
        + "\n  ".join(loi))
