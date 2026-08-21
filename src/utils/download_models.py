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
    "5CD-AI/Vintern-1B-v2"
]

# Model nào cần cho việc gì — tải cả 6 là ~15 GB, quá nhiều nếu chỉ chạy ETL text.
PROFILES = {
    "text-etl": ["BAAI/bge-m3"],                      # embedding chunk text
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

if __name__ == "__main__":
    main()
