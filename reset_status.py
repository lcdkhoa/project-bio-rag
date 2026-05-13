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
    """Reset toan bo image processing status."""
    status = ProcessingStatus()
    # Get all IDs from the collection
    all_data = status.db.get()
    if all_data and all_data.get("ids"):
        ids_to_delete = all_data["ids"]
        if ids_to_delete:
            status.db._collection.delete(ids=ids_to_delete)
            print(f"Da reset {len(ids_to_delete)} status entries")
    print("Da reset toan bo image status")


def reset_pdf_image_status(pdf_path: str):
    """Reset image status cho mot PDF cu the."""
    status = ProcessingStatus()
    pdf_hash = compute_file_hash(pdf_path)
    to_delete = [doc_id for doc_id in status._status_cache if doc_id.startswith(pdf_hash + "_page_")]
    if to_delete:
        status.db._collection.delete(ids=to_delete)
        print(f"Da reset {len(to_delete)} entries cho: {pdf_path}")
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
