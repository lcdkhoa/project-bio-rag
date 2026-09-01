import os
import argparse
from huggingface_hub import snapshot_download

# Redesign 2026-08 (D-19): text embedding -> BAAI/bge-m3, add cross-encoder
# BAAI/bge-reranker-v2-m3. MiniLM is a fallback only (via EMBEDDING_MODEL in
# .env) so it is no longer pre-fetched here.
MODELS = [
    "BAAI/bge-m3",
    "BAAI/bge-reranker-v2-m3",
    "Qwen/Qwen2.5-3B-Instruct",
    "openai/clip-vit-base-patch16",
    "google/owlvit-base-patch32",
    "5CD-AI/Vintern-1B-v2",
    "opendatalab/MinerU2.5-Pro-2605-1.2B",
]

# Model nào cần cho việc gì — tải cả 7 là ~17 GB, quá nhiều nếu chỉ chạy ETL text.
# D-158: "text-etl" từng CHỈ có bge-m3 trong khi `--text-only` đã cần MinerU cho
# bước hybrid công thức (D-56/D-144) từ trước lượt Colab 7 — model đó chưa từng
# được tải trước, nên dưới HF_HUB_OFFLINE=1 (đặt SAU bước tải) mọi lần
# `FormulaMinerUClient._load()` lazy-load lần đầu đều raise ngay (100% deterministic,
# đo được D-157/D-158). Server-side lazy download + offline flag là một tổ hợp
# không bao giờ hoạt động; phải tải trước như mọi model khác.
PROFILES = {
    "text-etl": ["BAAI/bge-m3",                        # embedding chunk text
                 "opendatalab/MinerU2.5-Pro-2605-1.2B"],  # hybrid OCR công thức
    "image-etl": ["openai/clip-vit-base-patch16",      # embed ảnh
                  "google/owlvit-base-patch32",        # detector phụ
                  "5CD-AI/Vintern-1B-v2"],             # caption ảnh
    "serve": ["BAAI/bge-m3", "BAAI/bge-reranker-v2-m3",
              "Qwen/Qwen2.5-3B-Instruct",
              "openai/clip-vit-base-patch16"],
    "all": list(MODELS),
}


def select_models(profile=None, only=None):
    """Danh sách model cần tải. `only` (tên ngắn, cách nhau dấu phẩy) thắng `profile`.

    Tên không nhận ra thì **raise** kèm danh sách hợp lệ — thà dừng còn hơn tải
    lặng lẽ sai thứ rồi để ETL chết ở bước sau vì thiếu model.
    """
    if only:
        by_short = {model_id.split("/")[-1]: model_id for model_id in MODELS}
        chosen, unknown = [], []
        for name in [part.strip() for part in only.split(",") if part.strip()]:
            if name in by_short:
                chosen.append(by_short[name])
            elif name in MODELS:
                chosen.append(name)
            else:
                unknown.append(name)
        if unknown:
            raise SystemExit(
                f"Không biết model {unknown}. Tên hợp lệ: {sorted(by_short)}")
        return chosen
    if profile:
        if profile not in PROFILES:
            raise SystemExit(
                f"Không biết profile {profile!r}. Hợp lệ: {sorted(PROFILES)}")
        return PROFILES[profile]
    return list(MODELS)


def main():
    parser = argparse.ArgumentParser(description="Download Hugging Face models for offline use.")
    parser.add_argument("--save_dir", type=str, default="./models", help="Directory to save the models")
    parser.add_argument("--profile", type=str, default=None,
                        help=f"Chỉ tải model cần cho một việc: {sorted(PROFILES)}")
    parser.add_argument("--only", type=str, default=None,
                        help="Chỉ tải các model này (tên ngắn, cách nhau dấu phẩy)")
    args = parser.parse_args()

    save_dir = os.path.abspath(args.save_dir)
    os.makedirs(save_dir, exist_ok=True)

    hf_token = os.getenv("HF_TOKEN")
    wanted = select_models(profile=args.profile, only=args.only)
    print(f"Sẽ tải {len(wanted)}/{len(MODELS)} model: {wanted}")

    # D-158: bản trước NUỐT exception rồi in "Failed to download ..." và vẫn
    # thoát mã 0 — một model thiếu (như MinerU trước bản vá này) trôi lặng lẽ
    # qua bước tải, và chỉ lộ ra hàng giờ sau dưới dạng ETL fail 100% dưới
    # HF_HUB_OFFLINE=1. Giờ ghi nhận model nào hỏng rồi THOÁT MÃ KHÁC 0 ở cuối
    # — dừng sớm rẻ hơn nhiều so với để cả một lượt ETL chạy trên model thiếu.
    that_bai: list[str] = []
    for model_id in wanted:
        print(f"Downloading {model_id}...")
        model_path = os.path.join(save_dir, model_id.split("/")[-1])
        try:
            snapshot_download(
                repo_id=model_id,
                local_dir=model_path,
                local_dir_use_symlinks=False,  # Download actual files so they can be copied to Google Drive
                token=hf_token
            )
            print(f"Successfully downloaded {model_id} to {model_path}\n")
        except Exception as e:
            print(f"Failed to download {model_id}: {e}\n")
            that_bai.append(model_id)

    if that_bai:
        print(f"[LỖI] {len(that_bai)}/{len(wanted)} model tải KHÔNG thành công: "
              f"{that_bai}. Dừng ở đây — đừng chạy ETL tiếp khi model chưa đủ.")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
