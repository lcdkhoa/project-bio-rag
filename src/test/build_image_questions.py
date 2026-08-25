"""48 câu hỏi sinh từ HÌNH — máy chọn crop, NGƯỜI nhìn ảnh và viết câu.

**Vì sao không tự động hoàn toàn (D-113, đo trên 938 crop của 4 quyển KNTT).**
Ba trường đọc lại từ pixel đều không đủ để sinh câu:

- `figure_caption` trùng chữ đã index của CHÍNH trang đó ở mức **trung vị 0,958**
  (73,3% có độ phủ >= 0,8) — câu sinh từ nó là câu VĂN BẢN đội lốt, và sẽ tái tạo
  đúng cái trần 0,104 của D-87. Lý do cấu trúc: caption trên KNTT phần lớn là câu
  lệnh bài tập quanh hình, không phải mô tả nội dung hình.
- `crop_text` độc lập với chữ trang thì **vỡ**: "H Mũi g là eì để Khi quản ụ Phối".
- `visual_caption_vi` là **0/938** — captioner tắt theo D-47 (nó bịa 4/12 và tự
  khai số hiệu hình SAI 4/4 lần).

Nên: máy chọn crop và bày ra mọi thứ nó đọc được, người **mở ảnh ra nhìn** rồi
viết câu hỏi + đáp án, hoặc gạch bỏ. Câu cuối cùng là của người. Đây cũng là lần
đầu bộ test của dự án có nhãn "người duyệt" thật cho phần mình sinh ra — pool 300
câu mới chỉ được duyệt trên MẪU 50 câu (D-90).

Hai bước, chạy rời nhau:

    python -m src.test.build_image_questions --chon      # máy chọn + chép crop + lập phiếu
    python -m src.test.build_image_questions --ap-dung   # trộn câu ĐÃ DUYỆT vào bộ 240

Phiếu theo đúng khuôn `document/review/ocr_gold/` mà người dùng đã quen:
`items.json` (máy xuất) + `phieu_nguoi.json` (`{_bat_dau, _ket_thuc, traloi}`).
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import chromadb

from src.config import PERSIST_DIR

BASE = Path(__file__).resolve().parent
OUT_DIR = Path("document/review/image_questions")
TESTSET_DIR = BASE / "testsets_240"

PER_BOOK = 4

# Chỉ lấy HÌNH thật, không lấy hộp chữ. `activity_box` / `textbook_info_box` là
# khung bài tập — chúng chính là thứ làm `figure_caption` trùng chữ trang.
FIGURE_TYPES = {"single_figure", "composite_figure", "sub_figure"}


def _client():
    return chromadb.PersistentClient(path=str(PERSIST_DIR))


def _page_texts() -> Dict[tuple, str]:
    col = _client().get_collection("biology_text")
    got = col.get(limit=100000, include=["metadatas", "documents"])
    pages: Dict[tuple, List[str]] = defaultdict(list)
    for m, d in zip(got["metadatas"], got["documents"]):
        pages[(m.get("source"), m.get("page"))].append(d or "")
    return {k: "\n".join(v) for k, v in pages.items()}


def _printed_page_map(books) -> Dict[str, Dict[int, int]]:
    """`{quyển: {chỉ số trang nguồn -> số trang IN}}`, đọc từ manifest.

    Vì sao không dùng thẳng `page_number` của image doc: nó là **chỉ số trang
    nguồn** (`page_num` trong `image_processor.py`), còn gold key của câu hỏi
    VĂN BẢN là **số trang IN** (`page` trong metadata chunk, thứ mà
    `ablation.py:422` đối chiếu). Hôm nay hai số bằng nhau vì offset = 0 trên
    12/12 quyển (D-65) — nhưng CLAUDE.md dặn thẳng: đừng đánh đồng chúng *về mặt
    thiết kế* dù chúng đang trùng. Trùng nhau là một phép đo của hôm nay, không
    phải một bảo đảm; đổi corpus một lần là 48 câu hỏi hình lệch một trang mà
    không ai thấy.
    """
    from src.config import MANIFEST_DIR
    from src.etl.book.manifest import book_id_from_source_name, load_manifest

    out: Dict[str, Dict[int, int]] = {}
    for book in books:
        man = load_manifest(
            Path(MANIFEST_DIR) / f"{book_id_from_source_name(book)}.json")
        out[book] = {int(p["page_index"]): p.get("printed_page")
                     for p in man.pages}
    return out


def _da_dung(out_dir: Path) -> tuple[dict, set]:
    """(số ô còn dùng được theo quyển, tập trang đã xuất hiện trong phiếu).

    Trang đã dùng bị loại khỏi lượt bù kể cả khi ô đó bị bỏ: nếu khung cắt của
    một trang đã hỏng thì lấy lại đúng trang đó nhiều khả năng cho ra khung hỏng
    tương tự, và người sẽ phải bỏ lần thứ hai.
    """
    p_items = out_dir / "items.json"
    p_phieu = out_dir / "phieu_nguoi.json"
    if not p_items.exists():
        return {}, set()
    items = {it["id"]: it for it in
             json.loads(p_items.read_text(encoding="utf-8"))}
    phieu = (json.loads(p_phieu.read_text(encoding="utf-8")).get("traloi", {})
             if p_phieu.exists() else {})

    con_lai: dict = defaultdict(int)
    trang_da_dung = set()
    for item_id, it in items.items():
        trang_da_dung.add((it["quyen"], it["trang"]))
        if not (phieu.get(item_id) or {}).get("bo"):
            con_lai[it["quyen"]] += 1
    return dict(con_lai), trang_da_dung


def chon(per_book: int, out_dir: Path, can_them: dict | None = None,
         tranh_trang: set | None = None) -> List[Dict]:
    """Chọn `per_book` hình MỖI QUYỂN, trải theo trang, chép crop ra để người xem.

    `can_them` (chế độ bù): `{quyển: số ô cần thêm}`. Quyển không có trong dict
    thì bỏ qua hẳn. `tranh_trang`: tập `(quyển, trang in)` không được lấy lại.

    Tiêu chí chọn cố ý ĐƠN GIẢN và giải thích được: hình thật (không phải hộp
    chữ), có `figure_label` (để trích dẫn kiểm được), và mỗi trang tối đa một
    hình (trải rộng). KHÔNG lọc theo độ phủ `crop_text` — người mới là nguồn ngữ
    nghĩa ở đây, nên chất lượng OCR của crop không phải tiêu chí chọn (D-113).
    """
    col = _client().get_collection("biology_image_metadata")
    got = col.get(limit=100000, include=["metadatas"])
    page_text = _page_texts()
    crop_dir = out_dir / "crops"
    printed = _printed_page_map(sorted({m.get("pdf_filename") for m in got["metadatas"]
                                        if m.get("pdf_filename")}))
    can_them = can_them or {}
    tranh_trang = tranh_trang or set()

    by_book: Dict[str, List[Dict]] = defaultdict(list)
    for m in got["metadatas"]:
        if (m.get("image_type") or "") not in FIGURE_TYPES:
            continue
        if not (m.get("figure_label") or "").strip():
            continue
        if not Path(m.get("image_path") or "").exists():
            continue
        by_book[m.get("pdf_filename") or "?"].append(m)

    out_dir.mkdir(parents=True, exist_ok=True)
    crop_dir.mkdir(parents=True, exist_ok=True)
    items: List[Dict] = []

    for book in sorted(by_book):
        muc_tieu = can_them.get(book, per_book) if can_them else per_book
        if muc_tieu <= 0:
            continue
        seen_pages = set()
        picked = []
        # sắp xếp xác định: theo trang rồi theo nhãn hình
        for m in sorted(by_book[book],
                        key=lambda x: (int(x.get("page_number") or 0),
                                       str(x.get("figure_label")))):
            page = int(m.get("page_number") or 0)
            if page in seen_pages:
                continue
            trang_in_thu = printed.get(book, {}).get(page)
            if (book, trang_in_thu) in tranh_trang:
                continue           # trang đã xuất hiện ở phiếu trước
            seen_pages.add(page)
            picked.append(m)
            if len(picked) >= muc_tieu:
                break

        for i, m in enumerate(picked, 1):
            page = int(m.get("page_number") or 0)          # chỉ số trang NGUỒN
            trang_in = printed.get(book, {}).get(page)     # số trang IN
            if trang_in is None:
                # Không quy đổi được thì BỎ ô, không mượn `page` làm trang in:
                # gold key sai một trang là chỉ học sinh tới sai chỗ (nguyên tắc 1).
                continue
            item_id = f"{book}_p{trang_in}_{i:02d}"
            dest = crop_dir / f"{item_id}.png"
            shutil.copyfile(m["image_path"], dest)
            items.append({
                "id": item_id,
                "quyen": book,
                "trang": trang_in,          # số trang IN — cùng hệ với gold key văn bản
                "trang_nguon": page,        # chỉ số trang nguồn, để lần lại file PNG
                "nhan_hinh": (m.get("figure_label") or "").strip(),
                "anh": dest.as_posix(),
                # ba trường đọc lại từ PIXEL — đưa nguyên trạng, kể cả khi vỡ,
                # để người thấy máy có gì mà tự đánh giá độ tin
                "figure_caption": (m.get("figure_caption") or "").strip(),
                "crop_text": (m.get("crop_text") or "").strip(),
                "chu_tren_trang": (page_text.get((book, trang_in)) or "")[:1500],
            })

    (out_dir / "items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


NHAP_PROMPT = """Bạn đang giúp soạn NHÁP cho một bộ kiểm thử sách giáo khoa KHTN.

Dưới đây là những gì máy đọc được QUANH một hình trong sách. Máy KHÔNG nhìn thấy
hình — chữ dưới đây do OCR nên có thể vỡ. Một người sẽ mở hình ra nhìn và sửa lại
câu của bạn, nên nhiệm vụ của bạn là cho họ một điểm khởi đầu, KHÔNG phải khẳng
định điều gì về hình.

Nhãn hình: {nhan_hinh}   (sách {quyen}, trang {trang})
Chú thích hình máy đọc được: {figure_caption}
Chữ đọc được TRONG hình: {crop_text}
Trích chữ trên trang: {chu_tren_trang}

Viết MỘT câu hỏi mà học sinh chỉ trả lời được khi NHÌN VÀO HÌNH, kèm đáp án ngắn.
Quy tắc:
- Câu hỏi phải nhắc tới {nhan_hinh}.
- Nếu chữ đọc được quá vỡ để biết hình vẽ gì, hãy đặt "chac_chan": false và viết
  câu hỏi tổng quát nhất có thể — ĐỪNG đoán chi tiết mình không đọc được.
- Đáp án ngắn gọn, tiếng Việt có dấu đầy đủ.

Trả về DUY NHẤT một JSON: {{"cau_hoi": "...", "dap_an": "...", "chac_chan": true/false}}"""


def nhap_bang_llm(items: List[Dict], out_dir: Path) -> Dict:
    """LLM viết NHÁP cho từng ô. Đây là nháp, không phải dữ liệu.

    D-113 đo được vì sao đây chỉ có thể là nháp: `figure_caption` trùng chữ trang
    ở mức trung vị 0,958 và `crop_text` độc lập thì vỡ. Nên mọi ô đều đi kèm
    `chac_chan` do chính model tự khai, và `--ap-dung` chỉ nhận câu NGƯỜI đã điền
    — nháp không bao giờ tự vào bộ test.
    """
    from src.test import eval_llm
    from src.test.generate_testsets import _ask_llm, _parse_json

    if not eval_llm.is_configured():
        raise SystemExit(eval_llm.config_help())
    llm = eval_llm.get_eval_llm(temperature=0.3)

    p = out_dir / "nhap_llm.json"
    nhap = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    loi = 0
    for i, it in enumerate(items, 1):
        if it["id"] in nhap:                 # chạy lại thì không gọi lại
            continue
        try:
            raw = _ask_llm(llm, NHAP_PROMPT.format(**it))
            d = _parse_json(raw)
            nhap[it["id"]] = {
                "cau_hoi": str(d.get("cau_hoi") or "").strip(),
                "dap_an": str(d.get("dap_an") or "").strip(),
                "chac_chan": bool(d.get("chac_chan")),
            }
        except Exception as exc:             # nháp hỏng thì bỏ trống, không bịa
            loi += 1
            nhap[it["id"]] = {"cau_hoi": "", "dap_an": "", "chac_chan": False,
                              "loi": str(exc)[:200]}
        p.write_text(json.dumps(nhap, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"  [{i}/{len(items)}] {it['id']} "
              f"{'OK' if nhap[it['id']]['cau_hoi'] else 'TRỐNG'}")
    return {"n": len(nhap), "loi": loi,
            "khong_chac": sum(1 for v in nhap.values() if not v.get("chac_chan")),
            "file": str(p)}


def lam_phieu(items: List[Dict], out_dir: Path) -> Path:
    """Phiếu để NGƯỜI điền. Không bao giờ ghi đè phiếu đã có.

    Nháp của LLM (nếu đã chạy `--nhap`) được điền sẵn vào `cau_hoi`/`dap_an` để
    người sửa thay vì gõ từ đầu, và `nhap_chac_chan` nói cho người biết model có
    tự tin hay không. Người vẫn phải MỞ ẢNH ra nhìn — nháp sinh từ chữ OCR vỡ.
    """
    p = out_dir / "phieu_nguoi.json"
    if p.exists():
        return p
    nhap_path = out_dir / "nhap_llm.json"
    nhap = json.loads(nhap_path.read_text(encoding="utf-8")) if nhap_path.exists() else {}
    phieu = {
        "_huong_dan": (
            "MỞ FILE ẢNH ở trường 'anh' của items.json ra NHÌN, rồi sửa 'cau_hoi' "
            "và 'dap_an' cho khớp với thứ NHÌN THẤY. Hai trường này có thể đã "
            "được LLM điền sẵn NHÁP — nháp sinh từ chữ OCR quanh hình, model "
            "KHÔNG nhìn thấy hình, nên phải kiểm chứ đừng tin. Câu phải trả lời "
            "được NHỜ hình, không phải nhờ chữ trên trang. Hình nào không dùng "
            "được thì đặt bo=true kèm lý do. Đừng sửa khoá 'id'."),
        "_bat_dau": int(time.time() * 1000),
        "_ket_thuc": 0,
        "traloi": {
            it["id"]: {
                "cau_hoi": (nhap.get(it["id"]) or {}).get("cau_hoi", ""),
                "dap_an": (nhap.get(it["id"]) or {}).get("dap_an", ""),
                "nhap_chac_chan": (nhap.get(it["id"]) or {}).get("chac_chan"),
                "bo": False, "ly_do_bo": "",
            }
            for it in items
        },
    }
    p.write_text(json.dumps(phieu, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


HTML_HEAD = """<!doctype html><meta charset="utf-8">
<title>Phiếu duyệt câu hỏi từ HÌNH</title>
<style>
 :root{color-scheme:light dark}
 body{font:15px/1.5 system-ui,sans-serif;margin:0;padding:24px;max-width:1100px;margin-inline:auto}
 h1{font-size:20px;margin:0 0 4px}
 .huong-dan{background:#fff8e1;color:#4a3b00;border-left:4px solid #e0a800;
            padding:12px 16px;border-radius:6px;margin:16px 0}
 @media(prefers-color-scheme:dark){.huong-dan{background:#3a3000;color:#ffe9a3}}
 .o{border:1px solid #8884;border-radius:10px;padding:16px;margin:18px 0;
    display:grid;grid-template-columns:minmax(260px,42%) 1fr;gap:18px}
 @media(max-width:820px){.o{grid-template-columns:1fr}}
 .o img{width:100%;height:auto;border:1px solid #8884;border-radius:6px;background:#fff}
 .ma{font:12px/1.45 ui-monospace,monospace;color:#8a8a8a;word-break:break-word}
 label{display:block;font-weight:600;margin:10px 0 4px;font-size:13px}
 textarea{width:100%;box-sizing:border-box;font:inherit;padding:8px;
          border:1px solid #8886;border-radius:6px;background:transparent;color:inherit}
 .bo{margin-top:10px;font-weight:600;color:#c0392b}
 .thanh{position:sticky;top:0;background:Canvas;padding:12px 0;border-bottom:1px solid #8884;
        display:flex;gap:12px;align-items:center;z-index:9}
 button{font:inherit;padding:8px 16px;border-radius:6px;border:1px solid #8886;
        background:#2d7ff9;color:#fff;cursor:pointer}
 .dem{color:#8a8a8a;font-size:13px}
 .nhan{display:inline-block;background:#8882;border-radius:4px;padding:1px 7px;
       font-size:12px;margin-right:6px}
 .khongchac{background:#e0a80033;color:#8a6d00}
</style>
<h1>Phiếu duyệt câu hỏi sinh từ HÌNH</h1>
<div class="thanh">
  <button onclick="xuat()">Tải phieu_nguoi.json</button>
  <span class="dem" id="dem"></span>
</div>
<div class="huong-dan">
  <b>Nhìn ảnh rồi mới viết.</b> Ô <i>Câu hỏi</i> và <i>Đáp án</i> đã được mô hình
  điền sẵn <b>nháp</b> — nháp sinh từ chữ OCR quanh hình, mô hình
  <b>KHÔNG nhìn thấy hình</b>, nên phải kiểm chứ đừng tin.
  <b>Sửa thoải mái, viết lại hẳn cũng được</b>: câu cuối cùng là của bạn.
  Hai ràng buộc duy nhất — (1) phải trả lời được <b>nhờ nhìn hình</b>, không phải
  nhờ đọc chữ trên trang; (2) đáp án đúng với thứ thực sự có trong hình.
</div>
<div class="huong-dan">
  <b>Khi nào tick “Bỏ khung cắt này”:</b> chỉ khi <b>bản thân khung cắt hỏng</b>,
  không liên quan tới câu hỏi. Bốn trường hợp:
  <b>(a)</b> cắt lấn hoặc cắt thiếu — nuốt cả đoạn văn, hoặc mất một nửa sơ đồ;
  <b>(b)</b> không phải hình — cắt nhầm bảng, khung chữ, hộp “Em có biết”;
  <b>(c)</b> không hỏi được — icon, logo, ảnh trang trí không mang nội dung khoa học;
  <b>(d)</b> trùng với một ô khác trong phiếu.
  Ô <i>lý do bỏ</i> không đi vào bộ test — nó để sửa ETL, nên ghi ngắn là đủ
  (“cắt lấn”, “là bảng”, “trùng ô trên”).
  Bỏ bao nhiêu cũng được, số thiếu sẽ được bù bằng hình khác.
</div>
"""

HTML_TAIL = """
<script>
const bd = Date.now();
function dem(){
  const o = document.querySelectorAll('.o').length;
  let xong = 0;
  document.querySelectorAll('.o').forEach(e=>{
    const bo = e.querySelector('.chk').checked;
    const q = e.querySelector('.q').value.trim();
    const a = e.querySelector('.a').value.trim();
    if (bo || (q && a)) xong++;
  });
  document.getElementById('dem').textContent = xong + '/' + o + ' ô đã xong';
}
document.addEventListener('input', dem);
document.addEventListener('change', dem);
dem();
function xuat(){
  const traloi = {};
  document.querySelectorAll('.o').forEach(e=>{
    traloi[e.dataset.id] = {
      cau_hoi: e.querySelector('.q').value.trim(),
      dap_an: e.querySelector('.a').value.trim(),
      bo: e.querySelector('.chk').checked,
      ly_do_bo: e.querySelector('.ldb').value.trim()
    };
  });
  const d = {_huong_dan: "Điền qua phieu.html", _bat_dau: bd,
             _ket_thuc: Date.now(), traloi: traloi};
  const b = new Blob([JSON.stringify(d, null, 1)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b); a.download = 'phieu_nguoi.json'; a.click();
}
</script>
"""


def _esc(x) -> str:
    return (str(x or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def lam_phieu_html(items: List[Dict], out_dir: Path) -> Path:
    """Trang HTML cục bộ: ảnh cạnh ô nhập, nháp điền sẵn, xuất lại JSON.

    Đọc nháp từ `nhap_llm.json` và câu người đã điền từ `phieu_nguoi.json` (nếu
    có) — mở lại trang giữa chừng thì không mất việc đã làm.
    """
    nhap_p = out_dir / "nhap_llm.json"
    nhap = json.loads(nhap_p.read_text(encoding="utf-8")) if nhap_p.exists() else {}
    cu_p = out_dir / "phieu_nguoi.json"
    cu = (json.loads(cu_p.read_text(encoding="utf-8")).get("traloi", {})
          if cu_p.exists() else {})

    phan = [HTML_HEAD]
    for it in items:
        n = nhap.get(it["id"]) or {}
        d = cu.get(it["id"]) or {}
        q = d.get("cau_hoi") or n.get("cau_hoi") or ""
        a = d.get("dap_an") or n.get("dap_an") or ""
        # ảnh nằm cùng thư mục với file HTML -> đường dẫn tương đối
        anh = "crops/" + Path(it["anh"]).name
        canh_bao = ("" if n.get("chac_chan") is not False else
                    '<span class="nhan khongchac">mô hình tự khai KHÔNG chắc</span>')
        phan.append(f"""
<div class="o" data-id="{_esc(it['id'])}">
  <div>
    <img src="{_esc(anh)}" alt="{_esc(it['id'])}" loading="lazy">
    <div class="ma"><b>{_esc(it['quyen'])}</b> · trang in {it['trang']} ·
      <span class="nhan">{_esc(it['nhan_hinh'])}</span>{canh_bao}</div>
    <div class="ma">chú thích máy đọc: {_esc(it['figure_caption'][:220]) or '(trống)'}</div>
    <div class="ma">chữ trong hình: {_esc(it['crop_text'][:220]) or '(trống)'}</div>
  </div>
  <div>
    <label>Câu hỏi</label>
    <textarea class="q" rows="4">{_esc(q)}</textarea>
    <label>Đáp án chuẩn</label>
    <textarea class="a" rows="3">{_esc(a)}</textarea>
    <div class="bo"><label style="display:inline">
      <input type="checkbox" class="chk"{' checked' if d.get('bo') else ''}>
      Bỏ khung cắt này (crop hỏng — KHÔNG phải câu hỏi sai)
    </label></div>
    <textarea class="ldb" rows="1" placeholder="lý do bỏ">{_esc(d.get('ly_do_bo'))}</textarea>
  </div>
</div>""")
    phan.append(HTML_TAIL)
    p = out_dir / "phieu.html"
    p.write_text("\n".join(phan), encoding="utf-8")
    return p


def ap_dung(out_dir: Path, testset_dir: Path) -> Dict:
    """Trộn câu ĐÃ DUYỆT vào bộ 240. Ô chưa điền / đã bỏ thì KHÔNG vào.

    Chạy lại nhiều lần cho cùng kết quả: mỗi lượt xoá câu `nguon_cau_hoi=hinh`
    cũ rồi ghi lại, nên không có chuyện chạy hai lần thành 96 câu.
    """
    items = {it["id"]: it for it in
             json.loads((out_dir / "items.json").read_text(encoding="utf-8"))}
    phieu = json.loads((out_dir / "phieu_nguoi.json").read_text(encoding="utf-8"))

    by_book: Dict[str, List[Dict]] = defaultdict(list)
    bo, trong = 0, 0
    for item_id, ans in phieu["traloi"].items():
        it = items.get(item_id)
        if it is None:
            continue
        if ans.get("bo"):
            bo += 1
            continue
        q = (ans.get("cau_hoi") or "").strip()
        a = (ans.get("dap_an") or "").strip()
        if not q or not a:
            trong += 1
            continue
        by_book[it["quyen"]].append({
            "question": q, "ground_truth": a,
            "source_book": it["quyen"], "source_page": it["trang"],
            "source_page_index": it.get("trang_nguon", it["trang"]),
            "do_kho": "truc_tiep",
            "nguon_cau_hoi": "hinh", "figure_label": it["nhan_hinh"],
        })

    them = 0
    for book, rows in sorted(by_book.items()):
        csv_path = testset_dir / f"{book}_testset.csv"
        if not csv_path.exists():
            raise SystemExit(f"Không thấy {csv_path} — chạy build_testset_240 trước")
        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            existing = list(csv.DictReader(f))
        fieldnames = list(existing[0].keys())
        existing = [r for r in existing if r.get("nguon_cau_hoi") != "hinh"]
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(existing)
            w.writerows([{k: r.get(k, "") for k in fieldnames} for r in rows])
        them += len(rows)

    return {"them": them, "bo": bo, "chua_dien": trong,
            "quyen": {b: len(r) for b, r in sorted(by_book.items())}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chon", action="store_true",
                    help="máy chọn crop + chép ảnh (chạy trước)")
    ap.add_argument("--bu", action="store_true",
                    help="chọn hình THAY THẾ cho những ô người đã tick Bỏ")
    ap.add_argument("--nhap", action="store_true",
                    help="LLM viết NHÁP câu hỏi (cần EVAL_LLM_* trong .env)")
    ap.add_argument("--phieu", action="store_true",
                    help="lập phiếu cho người (JSON + trang HTML xem ảnh)")
    ap.add_argument("--ap-dung", action="store_true",
                    help="trộn câu đã duyệt vào bộ 240")
    ap.add_argument("--per-book", type=int, default=PER_BOOK)
    ap.add_argument("--limit", type=int, default=0,
                    help="--nhap: chỉ viết nháp cho N ô đầu (thử đường chạy)")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    a = ap.parse_args()
    out_dir = Path(a.out_dir)

    if a.chon:
        items = chon(a.per_book, out_dir)
        per: Dict[str, int] = defaultdict(int)
        for it in items:
            per[it["quyen"]] += 1
        print(f"Chọn {len(items)} hình / {len(per)} quyển -> {out_dir}/items.json")
        for b, n in sorted(per.items()):
            mark = "" if n == a.per_book else f"   <-- THIẾU (cần {a.per_book})"
            print(f"  {b:18s} {n}{mark}")
        thieu = [b for b, n in per.items() if n < a.per_book]
        if thieu or len(per) < 12:
            print(f"CHƯA ĐỦ 12 quyển × {a.per_book} — ETL hình 12 quyển xong thì chạy lại.")
            return 1
        print("Bước tiếp: --nhap (LLM viết nháp) rồi --phieu (lập phiếu cho người).")
        return 0

    if a.bu:
        con_lai, tranh = _da_dung(out_dir)
        if not con_lai:
            print("Chưa có phiếu nào để bù. Chạy --chon trước.")
            return 2
        thieu = {b: a.per_book - n for b, n in con_lai.items()
                 if n < a.per_book}
        if not thieu:
            print(f"Không thiếu ô nào — mọi quyển đủ {a.per_book}.")
            return 0
        print(f"Thiếu: {thieu}  (tổng {sum(thieu.values())} ô)")
        them = chon(a.per_book, out_dir, can_them=thieu, tranh_trang=tranh)
        # Ghi NỐI vào items.json, không ghi đè: ô cũ người đã duyệt phải còn.
        p = out_dir / "items.json"
        cu = json.loads(p.read_text(encoding="utf-8"))
        cu_id = {x["id"] for x in cu}
        moi = [x for x in them if x["id"] not in cu_id]
        p.write_text(json.dumps(cu + moi, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"Đã thêm {len(moi)} ô vào items.json.")
        print("Bước tiếp: --nhap (chỉ gọi LLM cho ô mới) rồi --phieu.")
        print("LƯU Ý: --phieu KHÔNG ghi đè phiếu cũ. Đổi tên phieu_nguoi.json "
              "cũ thành phieu_nguoi_luot1.json trước, rồi trộn tay sau.")
        return 0

    if a.nhap:
        items = json.loads((out_dir / "items.json").read_text(encoding="utf-8"))
        if a.limit:
            items = items[:a.limit]
        r = nhap_bang_llm(items, out_dir)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        print("Nháp KHÔNG tự vào bộ test — phải qua --phieu rồi người duyệt.")
        return 0

    if a.phieu:
        items = json.loads((out_dir / "items.json").read_text(encoding="utf-8"))
        p = lam_phieu(items, out_dir)
        h = lam_phieu_html(items, out_dir)
        print(f"Phiếu JSON : {p}")
        print(f"Phiếu HTML : {h}")
        print("Mở file HTML bằng trình duyệt, nhìn ảnh rồi điền, bấm nút tải "
              "phieu_nguoi.json và chép đè file JSON trên.")
        return 0

    if a.ap_dung:
        r = ap_dung(out_dir, TESTSET_DIR)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["them"] else 1

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
