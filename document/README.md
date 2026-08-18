# Mục lục tài liệu

Điểm vào chính của dự án là [../README.md](../README.md). Thư mục này chứa tài liệu chi tiết.

| Tài liệu                                               | Dành cho ai           | Nội dung                                                                     |
| ------------------------------------------------------ | --------------------- | ---------------------------------------------------------------------------- |
| [technical_handover_rag.md](technical_handover_rag.md) | Người tiếp nhận / dev | Kiến trúc 4 khối, code flow, cấu trúc codebase, schema metadata ảnh          |
| [phat_trien_mo_rong.md](phat_trien_mo_rong.md)         | Người phát triển tiếp | Cách thêm sách, thêm biến thể NXB, tinh chỉnh retrieval, đổi model, thêm API |
| [huong_dan_van_hanh_rag.md](huong_dan_van_hanh_rag.md) | Người vận hành        | Lệnh CLI, CRUD metadata ảnh, các kịch bản, reset & xử lý sự cố               |
| [api_server_docs.md](api_server_docs.md)               | Frontend / tích hợp   | Tham chiếu Flask API: endpoint, request/response, ví dụ                      |
| [image_etl_technical.md](image_etl_technical.md)       | Dev ETL ảnh           | Thuật toán anchor-first, OWL-ViT, các loại vùng, tuning                      |
| [windows_tools_setup.md](windows_tools_setup.md)       | Cài đặt trên Windows  | Giải nén & khai báo path Poppler / Tesseract                                 |
| [tuturial.pdf](tuturial.pdf)                           | Tham khảo             | Slide/tutorial dạng PDF                                                      |

Runbook ETL ảnh theo từng nhà xuất bản: [../skills/etl-textbook-images/](../skills/etl-textbook-images/).

Hướng dẫn bộ đánh giá RAG: [../src/test/README.md](../src/test/README.md).

## Thứ tự đọc gợi ý cho người mới

1. [../README.md](../README.md) — tổng quan, cài đặt, quy trình.
2. [technical_handover_rag.md](technical_handover_rag.md) — hiểu kiến trúc & code flow.
3. [huong_dan_van_hanh_rag.md](huong_dan_van_hanh_rag.md) — vận hành thực tế.
4. [phat_trien_mo_rong.md](phat_trien_mo_rong.md) — khi cần mở rộng/phát triển.
