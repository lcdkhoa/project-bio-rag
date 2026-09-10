import os
import sys
import json
import time
import socket
import threading
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import urllib.parse
from playwright.sync_api import sync_playwright

WORKSPACE_DIR = r"d:\personal_repo\project_rag"
IMAGES_DIR = os.path.join(WORKSPACE_DIR, "database", "images")
OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "report", "tex_source", "src", "images", "chapter3")
FE_DIR = r"D:\personal_repo\project_rag_fe"

PHYSICS_RESPONSE = {
    "answer": (
        "Trong môn Khoa học tự nhiên 7, tốc độ chuyển động đặc trưng cho mức độ nhanh chậm của chuyển động, "
        "được xác định bằng quãng đường đi được trong một đơn vị thời gian:\n\n"
        "**Công thức tính tốc độ:**\n"
        "$$v = \\frac{s}{t}$$\n\n"
        "**Trong đó:** $v$ là tốc độ ($\\text{m/s}$ hoặc $\\text{km/h}$), $s$ là quãng đường ($\\text{m}$), $t$ là thời gian ($\\text{s}$).\n\n"
        "**Hệ thức suy ra và quy đổi đơn vị:** $1\\text{ m/s} = 3{,}6\\text{ km/h} \\qquad s = v \\cdot t \\qquad t = \\frac{s}{v}$"
    ),
    "answer_text": (
        "Trong môn Khoa học tự nhiên 7, tốc độ chuyển động đặc trưng cho mức độ nhanh chậm của chuyển động, "
        "được xác định bằng quãng đường đi được trong một đơn vị thời gian:\n\n"
        "**Công thức tính tốc độ:**\n"
        "$$v = \\frac{s}{t}$$\n\n"
        "**Trong đó:** $v$ là tốc độ ($\\text{m/s}$ hoặc $\\text{km/h}$), $s$ là quãng đường ($\\text{m}$), $t$ là thời gian ($\\text{s}$).\n\n"
        "**Hệ thức suy ra và quy đổi đơn vị:** $1\\text{ m/s} = 3{,}6\\text{ km/h} \\qquad s = v \\cdot t \\qquad t = \\frac{s}{v}$"
    ),
    "citations": [
        {
            "book": "Khoa học tự nhiên 7 (Kết nối tri thức)",
            "page": "42",
            "section": "Bài 8: Tốc độ chuyển động",
            "display": "SGK KHTN 7 KNTT tr. 42"
        },
        {
            "book": "Khoa học tự nhiên 7 (Chân trời sáng tạo)",
            "page": "49",
            "section": "Bài 8: Tốc độ chuyển động",
            "display": "SGK KHTN 7 CTST tr. 49"
        }
    ],
    "images": [
        {
            "image_path": "SGK_KHTN_7_KNTT/page_48_img_0.png",
            "image_url": "/images/SGK_KHTN_7_KNTT/page_48_img_0.png",
            "figure_label": "Hình 8.1",
            "figure_caption": "Thiết bị đo tốc độ sử dụng cổng quang điện và đồng hồ hiện số",
            "page": 48,
            "book": "Khoa học tự nhiên 7 (Kết nối tri thức)"
        },
        {
            "image_path": "SGK_KHTN_7_KNTT/page_49_img_0.png",
            "image_url": "/images/SGK_KHTN_7_KNTT/page_49_img_0.png",
            "figure_label": "Hình 8.2",
            "figure_caption": "Đo thời gian chuyển động trên máng nghiêng",
            "page": 49,
            "book": "Khoa học tự nhiên 7 (Kết nối tri thức)"
        },
        {
            "image_path": "SGK_KHTN_7_KNTT/page_51_img_0.png",
            "image_url": "/images/SGK_KHTN_7_KNTT/page_51_img_0.png",
            "figure_label": "Hình 9.1",
            "figure_caption": "Bảng ghi kết quả đo quãng đường và thời gian",
            "page": 51,
            "book": "Khoa học tự nhiên 7 (Kết nối tri thức)"
        }
    ]
}

CHEMISTRY_RESPONSE = {
    "answer": (
        "Khi cho dung dịch hydrochloric acid tác dụng với đá vôi (thành phần chính là calcium carbonate CaCO3), "
        "phản ứng xảy ra tạo muối calcium chloride, nước và giải phóng khí carbon dioxide:\n\n"
        "**Phương trình hóa học:**\n"
        "$$\\text{CaCO}_3 + 2\\text{HCl} \\rightarrow \\text{CaCl}_2 + \\text{CO}_2\\uparrow + \\text{H}_2\\text{O}$$\n\n"
        "**Hiện tượng thực nghiệm:** Mẩu đá vôi CaCO3 tan dần và có bọt khí không màu CO2 sủi bọt thoát ra mạnh do acid carbonic H2CO3 không bền bị phân hủy."
    ),
    "answer_text": (
        "Khi cho dung dịch hydrochloric acid tác dụng với đá vôi (thành phần chính là calcium carbonate CaCO3), "
        "phản ứng xảy ra tạo muối calcium chloride, nước và giải phóng khí carbon dioxide:\n\n"
        "**Phương trình hóa học:**\n"
        "$$\\text{CaCO}_3 + 2\\text{HCl} \\rightarrow \\text{CaCl}_2 + \\text{CO}_2\\uparrow + \\text{H}_2\\text{O}$$\n\n"
        "**Hiện tượng thực nghiệm:** Mẩu đá vôi CaCO3 tan dần và có bọt khí không màu CO2 sủi bọt thoát ra mạnh do acid carbonic H2CO3 không bền bị phân hủy."
    ),
    "citations": [
        {
            "book": "Khoa học tự nhiên 8 (Kết nối tri thức)",
            "page": "41",
            "section": "Bài 9: Acid",
            "display": "SGK KHTN 8 KNTT tr. 41"
        },
        {
            "book": "Khoa học tự nhiên 8 (Cánh diều)",
            "page": "45",
            "section": "Bài 8: Acid và tính chất",
            "display": "SGK KHTN 8 CD tr. 45"
        }
    ],
    "images": [
        {
            "image_path": "SGK_KHTN_8_KNTT/page_40_img_0.png",
            "image_url": "/images/SGK_KHTN_8_KNTT/page_40_img_0.png",
            "figure_label": "Hình 9.2",
            "figure_caption": "Thí nghiệm dung dịch HCl tác dụng với đá vôi CaCO3",
            "page": 40,
            "book": "Khoa học tự nhiên 8 (Kết nối tri thức)"
        },
        {
            "image_path": "SGK_KHTN_8_KNTT/page_41_img_0.png",
            "image_url": "/images/SGK_KHTN_8_KNTT/page_41_img_0.png",
            "figure_label": "Hình 9.3",
            "figure_caption": "Thu khí carbon dioxide CO2 sinh ra từ phản ứng",
            "page": 41,
            "book": "Khoa học tự nhiên 8 (Kết nối tri thức)"
        },
        {
            "image_path": "SGK_KHTN_8_KNTT/page_42_img_0.png",
            "image_url": "/images/SGK_KHTN_8_KNTT/page_42_img_0.png",
            "figure_label": "Hình 9.4",
            "figure_caption": "Sơ đồ chuyển hóa hóa học của hợp chất vô cơ",
            "page": 42,
            "book": "Khoa học tự nhiên 8 (Kết nối tri thức)"
        }
    ]
}

class MockRagHandler(BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy"}')
            return

        if path.startswith("/images/"):
            rel_path = path[len("/images/"):]
            local_path = os.path.join(IMAGES_DIR, rel_path.replace("/", os.sep))
            if os.path.isfile(local_path):
                with open(local_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                if local_path.endswith(".png"):
                    self.send_header("Content-Type", "image/png")
                elif local_path.endswith(".jpg") or local_path.endswith(".jpeg"):
                    self.send_header("Content-Type", "image/jpeg")
                else:
                    self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                try:
                    self.wfile.write(content)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body.decode("utf-8")) if body else {}
        q = data.get("question", "").lower()

        if "tốc độ" in q or "vận tốc" in q or "v =" in q or "lí" in q or "vật lí" in q:
            resp_data = PHYSICS_RESPONSE
        else:
            resp_data = CHEMISTRY_RESPONSE

        if path == "/api/chat/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            try:
                self.wfile.write(b'event: status\ndata: {"status": "retrieving"}\n\n')
                self.wfile.flush()
                time.sleep(0.15)

                self.wfile.write(b'event: status\ndata: {"status": "answering"}\n\n')
                self.wfile.flush()
                time.sleep(0.15)

                delta_payload = json.dumps({"delta": resp_data["answer_text"]}, ensure_ascii=False)
                self.wfile.write(f"event: answer_delta\ndata: {delta_payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.15)

                done_payload = json.dumps(resp_data, ensure_ascii=False)
                self.wfile.write(f"event: done\ndata: {done_payload}\n\n".encode("utf-8"))
                self.wfile.flush()
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass
            return

        if path == "/api/chat":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp_data, ensure_ascii=False).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        pass

def run_mock_server(port=5000):
    server = ThreadingHTTPServer(("127.0.0.1", port), MockRagHandler)
    server.serve_forever()

def wait_for_port(port, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False

def main():
    print("Starting Multi-threaded Mock RAG server on port 5000...")
    mock_thread = threading.Thread(target=run_mock_server, args=(5000,), daemon=True)
    mock_thread.start()

    if not wait_for_port(5000, 5):
        print("Error: Mock server failed to start.")
        sys.exit(1)
    print("Mock RAG server is listening on port 5000.")

    print("Starting Next.js frontend on port 3000...")
    fe_proc = subprocess.Popen(
        ["npx", "next", "start", "-p", "3000"],
        cwd=FE_DIR,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    if not wait_for_port(3000, 20):
        print("Error: Next.js frontend failed to start on port 3000.")
        fe_proc.terminate()
        sys.exit(1)
    print("Next.js frontend is listening on port 3000.")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        with sync_playwright() as p:
            print("Launching Playwright Chromium...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1205, "height": 910}, device_scale_factor=1)
            page = context.new_page()

            print("Initializing session in frontend...")
            page.goto("http://localhost:3000")
            page.wait_for_load_state("networkidle")
            page.evaluate("""() => {
                localStorage.setItem('rag_user_name', 'Đăng Khoa');
                localStorage.setItem('rag_api_host', 'http://localhost:5000');
            }""")
            page.reload()
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("textarea", timeout=10000)
            print("Frontend loaded with ChatInterface.")

            # --- 1. Physics Screenshot ---
            print("\nExecuting Physics formula Q&A...")
            physics_q = "Công thức tính tốc độ chuyển động và giải thích các đại lượng?"
            page.fill("textarea", physics_q)
            time.sleep(0.3)
            page.keyboard.press("Enter")

            print("Waiting for KaTeX and citations...")
            page.wait_for_selector(".katex", timeout=15000)
            page.wait_for_selector("text=Nguồn trích dẫn", timeout=15000)
            page.wait_for_selector("img[alt*='Hình 8.1']", timeout=10000)
            time.sleep(2.0)

            # Scroll user message to top
            page.evaluate("""() => {
                const userMsg = document.querySelector('.flex-row-reverse');
                if (userMsg) {
                    userMsg.scrollIntoView({ behavior: 'instant', block: 'start' });
                }
            }""")
            time.sleep(1.0)

            physics_img_path = os.path.join(OUTPUT_DIR, "fe-formula-physics.png")
            page.screenshot(path=physics_img_path)
            print(f"Saved Physics screenshot: {physics_img_path}")

            # --- 2. Chemistry Screenshot ---
            print("\nExecuting Chemistry formula Q&A...")
            page.reload()
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("textarea", timeout=10000)

            chem_q = "Viết phương trình hóa học khi cho hydrochloric acid HCl tác dụng với đá vôi CaCO3."
            page.fill("textarea", chem_q)
            time.sleep(0.3)
            page.keyboard.press("Enter")

            print("Waiting for KaTeX and citations...")
            page.wait_for_selector(".katex", timeout=15000)
            page.wait_for_selector("text=Nguồn trích dẫn", timeout=15000)
            page.wait_for_selector("img[alt*='Hình 9.2']", timeout=10000)
            time.sleep(2.0)

            page.evaluate("""() => {
                const userMsg = document.querySelector('.flex-row-reverse');
                if (userMsg) {
                    userMsg.scrollIntoView({ behavior: 'instant', block: 'start' });
                }
            }""")
            time.sleep(1.0)

            chem_img_path = os.path.join(OUTPUT_DIR, "fe-formula-chemistry.png")
            page.screenshot(path=chem_img_path)
            print(f"Saved Chemistry screenshot: {chem_img_path}")

            browser.close()
    finally:
        print("Cleaning up Next.js process...")
        subprocess.run(f"taskkill /F /T /PID {fe_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Done!")

if __name__ == "__main__":
    main()
