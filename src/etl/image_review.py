"""Manual review utilities for image metadata quality control."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from langchain_core.documents import Document

from ..config import IMAGE_REVIEW_MANIFEST_PATH

logger = logging.getLogger(__name__)


class ImageReviewManager:
    """Export/apply human review updates for extracted images."""

    def __init__(self, manifest_path: Path = IMAGE_REVIEW_MANIFEST_PATH):
        self.manifest_path = Path(manifest_path)

    def _read_manifest_records(self) -> Dict[str, dict]:
        if not self.manifest_path.exists():
            return {}

        records: Dict[str, dict] = {}
        try:
            for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                image_id = str(payload.get("image_id") or "").strip()
                if not image_id:
                    continue
                records[image_id] = payload
        except Exception as e:
            logger.warning(f"Could not read image review manifest: {e}")
        return records

    def _write_manifest_records(self, records: Dict[str, dict]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        sorted_records = sorted(
            records.values(),
            key=lambda row: (
                str(row.get("pdf_filename") or ""),
                int(row.get("page_number") or 0),
                str(row.get("image_path") or ""),
            ),
        )
        with self.manifest_path.open("w", encoding="utf-8") as handle:
            for record in sorted_records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _build_search_text(self, metadata: dict) -> str:
        caption_text = metadata.get("caption_vi_manual", "") or metadata.get("caption_vi", "") or metadata.get("caption", "")
        keywords_text = metadata.get("keywords_vi_manual", "") or metadata.get("keywords_vi", "")
        parts = [
            metadata.get("figure_label", ""),
            metadata.get("figure_caption", ""),
            metadata.get("section_title", ""),
            metadata.get("image_type", ""),
            keywords_text,
            caption_text,
            metadata.get("context_text", ""),
            f"Trang {metadata.get('page_number', '')}",
            metadata.get("pdf_filename", ""),
        ]
        return "\n".join(str(part).strip() for part in parts if str(part).strip())

    def export_for_review(
        self,
        output_path: str,
        pdf_filename: Optional[str] = None,
        only_pending: bool = True,
    ) -> int:
        records = self._read_manifest_records()
        rows = []
        for record in records.values():
            if pdf_filename and str(record.get("pdf_filename") or "") != pdf_filename:
                continue

            review_status = str(record.get("review_status") or "pending")
            if only_pending and review_status not in {"pending", ""}:
                continue

            rows.append(
                {
                    "image_id": record.get("image_id", ""),
                    "pdf_filename": record.get("pdf_filename", ""),
                    "page_number": record.get("page_number", ""),
                    "image_path": record.get("image_path", ""),
                    "page_snapshot_path": record.get("page_snapshot_path", ""),
                    "bbox": record.get("bbox", ""),
                    "figure_label": record.get("figure_label", ""),
                    "figure_caption": record.get("figure_caption", ""),
                    "caption_vi": record.get("caption_vi", ""),
                    "keywords_vi": record.get("keywords_vi", ""),
                    "caption_vi_manual": record.get("caption_vi_manual", ""),
                    "keywords_vi_manual": record.get("keywords_vi_manual", ""),
                    "review_status": review_status or "pending",
                    "is_active": bool(record.get("is_active", True)),
                    "review_notes": record.get("review_notes", ""),
                }
            )

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"Exported {len(rows)} review rows to {output_file}")
        return len(rows)

    def apply_review_updates(self, review_path: str, reviewed_by: str = "human") -> dict:
        review_file = Path(review_path)
        if not review_file.exists():
            raise FileNotFoundError(f"Review file not found: {review_file}")

        payload = json.loads(review_file.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Review file must be a JSON array")

        records = self._read_manifest_records()
        if not records:
            return {"updated": 0, "deleted": 0, "upserted": 0}

        changed: Dict[str, dict] = {}
        deleted_ids: List[str] = []
        now = datetime.now().isoformat()

        for update in payload:
            if not isinstance(update, dict):
                continue
            image_id = str(update.get("image_id") or "").strip()
            if not image_id or image_id not in records:
                continue

            record = dict(records[image_id])
            status = str(update.get("review_status") or record.get("review_status") or "pending").strip().lower()
            if update.get("delete") is True:
                status = "rejected"

            record["review_status"] = status
            record["review_notes"] = str(update.get("review_notes") or record.get("review_notes") or "").strip()
            record["reviewed_by"] = str(update.get("reviewed_by") or reviewed_by).strip()
            record["reviewed_at"] = now

            caption_manual = str(update.get("caption_vi_manual") or record.get("caption_vi_manual") or "").strip()
            keywords_manual = str(update.get("keywords_vi_manual") or record.get("keywords_vi_manual") or "").strip()
            record["caption_vi_manual"] = caption_manual
            record["keywords_vi_manual"] = keywords_manual

            is_active = bool(update.get("is_active", record.get("is_active", True)))
            if status in {"rejected", "deleted"}:
                is_active = False
            if status in {"approved", "edited"} and not is_active:
                is_active = True
            record["is_active"] = is_active

            record["final_caption_vi"] = caption_manual or str(record.get("caption_vi") or record.get("caption") or "")
            record["final_keywords_vi"] = keywords_manual or str(record.get("keywords_vi") or "")
            record["search_text"] = self._build_search_text(record)
            record["updated_at"] = now

            records[image_id] = record
            changed[image_id] = record
            if not is_active:
                deleted_ids.append(image_id)

        if not changed:
            return {"updated": 0, "deleted": 0, "upserted": 0}

        self._write_manifest_records(records)

        from ..rag.image_vectorstore import ImageVectorDB

        vdb = ImageVectorDB()
        if deleted_ids:
            vdb.delete_documents(deleted_ids)

        docs_to_upsert = [
            Document(page_content=str(row.get("search_text") or ""), metadata=row)
            for image_id, row in changed.items()
            if image_id not in deleted_ids
        ]
        if docs_to_upsert:
            vdb.add_documents(docs_to_upsert)

        summary = {
            "updated": len(changed),
            "deleted": len(deleted_ids),
            "upserted": len(docs_to_upsert),
        }
        logger.info(f"Applied image review updates: {summary}")
        return summary
