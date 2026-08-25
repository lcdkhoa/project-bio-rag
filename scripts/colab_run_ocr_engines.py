# -*- coding: utf-8 -*-
"""Chạy các engine OCR ứng viên trên 97 crop của bake-off. **CHẠY TRÊN COLAB GPU.**

Máy dev là `torch 2.11.0+cpu`, không có CUDA — một VLM 1–3 B đọc 97 crop trên CPU
là hàng giờ. Nên file này sống ở `scripts/` và được chạy từ notebook Colab, không
từ `main.py`.

## Đầu vào / đầu ra

    vào : <crops>/crops.json  + <crops>/<id>.png     (do `--export` sinh, 8,2 MB)
    ra  : engine_<ten>.json   = {"<id ô>": "<chữ engine đọc được>"}

Chép `engine_*.json` về `database/review/ocr_gold/` rồi chấm bằng:

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

def _qwen_style(model_id: str):
    """Đường chung cho VLM theo giao diện chat của transformers.

    Dùng được cho `Nanonets-OCR2-3B`, `dots.ocr`, và các model cùng họ Qwen2-VL.
    Colab cần `transformers` mới (máy dev đang 4.46.3 — quá cũ cho nhóm này).
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoProcessor

    proc = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_id, trust_remote_code=True, torch_dtype=torch.bfloat16,
        device_map="auto")
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
    print("Chép file này về database/review/ocr_gold/ rồi:")
    print("  python -m src.test.ocr_bakeoff --compare")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
