"""Reset ETL processing status."""

from src.etl.processing_status import ProcessingStatus, compute_file_hash
from src.config import PERSIST_DIR, IMAGE_COLLECTION_NAME, IMAGE_METADATA_COLLECTION_NAME
import glob


def reset_image_vector_indexes():
    """Reset visual and metadata image vector collections."""
    import chromadb

    client = chromadb.PersistentClient(path=str(PERSIST_DIR))
    for collection_name in (IMAGE_COLLECTION_NAME, IMAGE_METADATA_COLLECTION_NAME):
        try:
            client.delete_collection(collection_name)
            print(f"Da xoa image vector collection: {collection_name}")
        except Exception:
            print(f"Khong tim thay collection de xoa: {collection_name}")


def reset_all_image_status():
    """Reset toan bo image processing status while preserving text status."""
    status = ProcessingStatus()
    reset_count = 0
    for current in list(status._status_cache.values()):
        status.update_status(
            pdf_hash=current["pdf_hash"],
            page_number=current["page_number"],
            text_indexed=current.get("text_indexed", False),
            image_extracted=False,
            pdf_filename=current.get("pdf_filename"),
        )
        reset_count += 1
    print(f"Da reset image status cho {reset_count} trang")


def reset_pdf_image_status(pdf_path: str):
    """Reset image status cho mot PDF cu the."""
    status = ProcessingStatus()
    pdf_hash = compute_file_hash(pdf_path)
    matching_statuses = [
        current
        for doc_id, current in status._status_cache.items()
        if doc_id.startswith(pdf_hash + "_page_")
    ]
    if matching_statuses:
        for current in matching_statuses:
            status.update_status(
                pdf_hash=current["pdf_hash"],
                page_number=current["page_number"],
                text_indexed=current.get("text_indexed", False),
                image_extracted=False,
                pdf_filename=current.get("pdf_filename"),
            )
        print(f"Da reset image status cho {len(matching_statuses)} trang: {pdf_path}")
    else:
        print(f"Khong co status nao de reset cho: {pdf_path}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        reset_all_image_status()
    elif len(sys.argv) > 1 and sys.argv[1] == "--image-index":
        reset_image_vector_indexes()
    elif len(sys.argv) > 1 and sys.argv[1] == "--images-full":
        reset_all_image_status()
        reset_image_vector_indexes()
    elif len(sys.argv) > 1:
        reset_pdf_image_status(sys.argv[1])
    else:
        print("Usage:")
        print("  python reset_status.py --all     # Reset tat ca image status")
        print("  python reset_status.py --image-index     # Reset image vector collections")
        print("  python reset_status.py --images-full     # Reset image status + image vector collections")
        print("  python reset_status.py <path>    # Reset chi mot PDF")
