# -*- coding: utf-8 -*-
"""Chạy các engine OCR ứng viên trên 97 crop của bake-off. **CHẠY TRÊN COLAB GPU.**

Máy dev là `torch 2.11.0+cpu`, không có CUDA — một VLM 1–3 B đọc 97 crop trên CPU
là hàng giờ. Nên file này sống ở `scripts/` và được chạy từ notebook Colab, không
từ `main.py`.

## Đầu vào / đầu ra

    vào : <crops>/crops.json  + <crops>/<id>.png     (do `--export` sinh, 8,2 MB)
    ra  : engine_<ten>.json   = {"<id ô>": "<chữ engine đọc được>"}

Chép `engine_*.json` về `document/review/ocr_gold/` rồi chấm bằng:

    python -m src.test.ocr_bakeoff --compare

## Vì sao chạy trên CROP chứ không trên cả trang

Bake-off phải **công bằng**, không phải giống production. Engine và người duyệt
chấm trên **cùng một mẩu pixel**; nếu để engine đọc cả trang rồi ta đi tìm dòng
nào khớp nhất với đáp án của người, đó là **tự chọn kết quả tốt nhất cho engine**
— một phép đo thiên vị. Ô loại BẢNG có crop là cả **dải bảng**, nên engine vẫn
phải làm đúng việc khó (giữ quan hệ hàng/cột), chỉ là không phải tự tìm bảng ở đâu.

Sau khi CHỌN được model, production mới cho nó đọc **cả trang** — đó là bước 1
của thiết kế, và nó cần phép đo này trước.

## CẤM

- Không sửa `crops.json` để "giúp" engine.
- Không bỏ qua ô engine đọc lỗi: ghi chuỗi rỗng, để `--compare` tính là SAI.
  Bỏ qua sẽ thưởng cho engine im lặng (bài học D-83).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Nhắc: `prompt` phải yêu cầu TRẢ NGUYÊN VĂN, không diễn giải, không dịch.
PROMPT_DONG = (
    "Trích xuất chính xác toàn bộ chữ trong ảnh này. Giữ nguyên tiếng Việt có "
    "dấu. Giữ nguyên chỉ số dưới trong công thức hoá học (O₂, H₂SO₄, CO₂). "
    "Chỉ trả về phần chữ, không giải thích, không dịch."
)
PROMPT_BANG = (
    "Trích xuất bảng trong ảnh này thành Markdown. Giữ nguyên tiếng Việt có "
    "dấu, giữ nguyên dấu phẩy thập phân (ví dụ 26,2 chứ không phải 262), và "
    "giữ đúng số cột. Chỉ trả về bảng Markdown, không giải thích."
)


def prompt_for(kind: str) -> str:
    return PROMPT_BANG if kind == "bang" else PROMPT_DONG


def load_crops(crops_dir: Path):
    man = json.loads((crops_dir / "crops.json").read_text(encoding="utf-8"))
    for it in man:
        p = crops_dir / it["file"]
        if not p.exists():
            raise FileNotFoundError(
                f"Thiếu {p} — crops.json và thư mục không khớp. Dựng lại bằng "
                "`python -m src.test.ocr_bakeoff --export`.")
    return man


# --- Các engine ----------------------------------------------------------
# Mỗi engine là một hàm nhận (đường dẫn PNG, prompt) -> chuỗi. Thêm engine mới
# thì thêm một hàm và một dòng trong ENGINES; không sửa vòng chạy.

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


def _load_vlm(model_id: str, torch):
    """Nạp VLM bằng auto-class ĐÚNG cho model đó, và NÓI RA dùng class nào.

    Không thử-rồi-nuốt: mọi lỗi được giữ lại, và nếu không class nào nạp được thì
    raise kèm ĐỦ danh sách lỗi. Một fallback im lặng ở đây sẽ khiến engine chạy
    bằng đường không ai kiểm — đúng bệnh đã cắn năm lần (D-68, D-75, D-83, D-84, D-94).
    """
    import transformers

    # `torch_dtype` bị bỏ ở transformers 5.x, `dtype` chỉ có từ 4.56. Chọn theo
    # phiên bản THẬT trên Colab thay vì đoán.
    major = int(str(transformers.__version__).split(".")[0])
    dtype_kw = ({"dtype": torch.bfloat16} if major >= 5
                else {"torch_dtype": torch.bfloat16})

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
        if not _tie_da_xay_ra(model) and _khai_bao_tie(model_id):
            print("[vá] lm_head CHƯA được buộc với embedding dù model khai "
                  "tie_word_embeddings=True -> gọi tie_weights()", flush=True)
            model.tie_weights()
            if not _tie_da_xay_ra(model):
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


def _qwen_style(model_id: str):
    """Đường chung cho VLM theo giao diện chat của transformers.

    Dùng được cho `Nanonets-OCR2-3B` (Qwen2.5-VL), `MinerU2.5` (Qwen2-VL) và
    `dots.ocr` (code riêng, khai qua `auto_map`). Class nạp model KHÔNG cố định —
    xem `_load_vlm`. Colab cần `transformers` mới (máy dev đang 4.46.3 — quá cũ).
    """
    import torch
    from transformers import AutoProcessor

    proc = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    model = _load_vlm(model_id, torch)
    model.eval()

    def run(png: Path, prompt: str) -> str:
        from PIL import Image

        img = Image.open(png).convert("RGB")
        msgs = [{"role": "user", "content": [
            {"type": "image"}, {"type": "text", "text": prompt}]}]
        text = proc.apply_chat_template(msgs, tokenize=False,
                                        add_generation_prompt=True)
        inputs = proc(text=[text], images=[img], return_tensors="pt").to(
            model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=512, do_sample=False)
        gen = out[0][inputs["input_ids"].shape[1]:]
        return proc.decode(gen, skip_special_tokens=True).strip()

    return run


def _paddleocr_vl():
    """PaddleOCR-VL 1.6 (0,9 B) — nhỏ nhất trong bốn ứng viên."""
    from paddleocr import PaddleOCRVL

    pipe = PaddleOCRVL()

    def run(png: Path, prompt: str) -> str:
        res = pipe.predict(str(png))
        parts = []
        for r in res:
            md = getattr(r, "markdown", None) or (
                r.get("markdown") if isinstance(r, dict) else None)
            if isinstance(md, dict):
                md = md.get("markdown_texts", "")
            if md:
                parts.append(str(md))
        return "\n".join(parts).strip()

    return run


ENGINES = {
    "paddleocr_vl": _paddleocr_vl,
    "nanonets_ocr2_3b": lambda: _qwen_style("nanonets/Nanonets-OCR2-3B"),
    "dots_ocr": lambda: _qwen_style("dots-studio/dots.ocr"),
    "mineru25": lambda: _qwen_style("opendatalab/MinerU2.5-Pro-2605-1.2B"),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engine", required=True, choices=sorted(ENGINES),
                    help="Chạy MỘT engine mỗi lượt: phiên Colab hay đứt, và mỗi "
                         "engine cần bộ thư viện khác nhau.")
    ap.add_argument("--crops-dir", required=True)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--limit", type=int, default=0,
                    help="Chạy thử vài ô trước khi chạy cả 97.")
    args = ap.parse_args()

    crops_dir = Path(args.crops_dir)
    man = load_crops(crops_dir)
    if args.limit:
        man = man[: args.limit]

    print(f"[{args.engine}] nạp model …", flush=True)
    t0 = time.time()
    try:
        run = ENGINES[args.engine]()
    except Exception as exc:
        # THOÁT KHÁC 0, và nói rõ thiếu gì. Trước bản vá này lỗi nạp model chỉ
        # in traceback rồi cell notebook chạy tiếp sang `--compare`, in ra bảng
        # baseline trông như một kết quả bình thường — đúng cái bệnh D-83: một
        # bước thất bại mà lớp gọi nó vẫn báo thành công.
        print(f"\n!! NẠP MODEL THẤT BẠI: {type(exc).__name__}: {exc}")
        print(f"!! Engine {args.engine!r} CHƯA chạy. KHÔNG có engine_"
              f"{args.engine}.json nào được ghi.")
        if "paddle" in str(exc).lower():
            print("!! PaddleOCR cần `paddlepaddle` (framework) cài RIÊNG, và bản "
                  "GPU không nằm trên PyPI. Dùng engine khác trước — ba engine "
                  "kia chỉ cần `transformers`.")
        return 3
    print(f"[{args.engine}] nạp xong trong {time.time() - t0:.0f}s", flush=True)

    out_path = Path(args.out_dir) / f"engine_{args.engine}.json"
    ket_qua = {}
    if out_path.exists():
        # Nối tiếp: phiên Colab đứt giữa chừng thì không mất phần đã chạy.
        ket_qua = json.loads(out_path.read_text(encoding="utf-8"))
        print(f"[{args.engine}] nối tiếp {len(ket_qua)} ô đã có")

    t0 = time.time()
    for i, it in enumerate(man, 1):
        if it["id"] in ket_qua:
            continue
        try:
            ket_qua[it["id"]] = run(crops_dir / it["file"],
                                    prompt_for(it.get("kind", "")))
        except Exception as exc:
            # Ghi chuỗi RỖNG, không bỏ qua: bỏ qua sẽ thưởng cho engine im lặng
            # và `--compare` sẽ chấm nó trên ít ô hơn (bài học D-83).
            print(f"  !! {it['id']} lỗi: {type(exc).__name__}: {exc}")
            ket_qua[it["id"]] = ""
        if i % 5 == 0 or i == len(man):
            el = time.time() - t0
            print(f"[{args.engine}] {i}/{len(man)}  {el:.0f}s  "
                  f"{el / max(1, i):.1f}s/ô", flush=True)
            out_path.write_text(json.dumps(ket_qua, ensure_ascii=False, indent=1),
                                encoding="utf-8")
    out_path.write_text(json.dumps(ket_qua, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    rong = sum(1 for v in ket_qua.values() if not str(v).strip())
    print(f"\n[{args.engine}] xong {len(ket_qua)} ô, {rong} ô rỗng -> {out_path}")
    print("Chép file này về document/review/ocr_gold/ rồi:")
    print("  python -m src.test.ocr_bakeoff --compare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
