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

BIOLOGY_RESPONSE = {
    "answer": (
        "Quang hợp là quá trình lá cây sử dụng nước và khí carbon dioxide CO2, "
        "nhờ năng lượng ánh sáng mặt trời được lục lạp hấp thụ, để tổng hợp chất hữu cơ (glucose C6H12O6) "
        "và giải phóng khí oxygen O2:\n\n"
        "**Phương trình hóa học tổng quát:**\n"
        "$$\\text{6CO}_2 + \\text{6H}_2\\text{O} \\xrightarrow{\\text{Ánh sáng, Diệp lục}} \\text{C}_6\\text{H}_{12}\\text{O}_6 + \\text{6O}_2\\uparrow$$\n\n"
        "**Vai trò của quang hợp:** Cung cấp chất hữu cơ nuôi sống sinh giới, cung cấp khí oxygen duy trì sự sống "
        "và điều hòa khí hậu toàn cầu."
    ),
    "answer_text": (
        "Quang hợp là quá trình lá cây sử dụng nước và khí carbon dioxide CO2, "
        "nhờ năng lượng ánh sáng mặt trời được lục lạp hấp thụ, để tổng hợp chất hữu cơ (glucose C6H12O6) "
        "và giải phóng khí oxygen O2:\n\n"
        "**Phương trình hóa học tổng quát:**\n"
        "$$\\text{6CO}_2 + \\text{6H}_2\\text{O} \\xrightarrow{\\text{Ánh sáng, Diệp lục}} \\text{C}_6\\text{H}_{12}\\text{O}_6 + \\text{6O}_2\\uparrow$$\n\n"
        "**Vai trò của quang hợp:** Cung cấp chất hữu cơ nuôi sống sinh giới, cung cấp khí oxygen duy trì sự sống "
        "và điều hòa khí hậu toàn cầu."
    ),
    "citations": [
        {
            "book": "Khoa học tự nhiên 7 (Kết nối tri thức)",
            "page": "101",
            "section": "Bài 23: Quang hợp ở thực vật",
            "display": "SGK KHTN 7 KNTT tr. 101"
        },
        {
            "book": "Khoa học tự nhiên 7 (Chân trời sáng tạo)",
            "page": "108",
            "section": "Bài 21: Quang hợp",
            "display": "SGK KHTN 7 CTST tr. 108"
        }
    ],
    "images": [
        {
            "image_path": "SGK_KHTN_7_KNTT/page_101_img_0.png",
            "image_url": "/images/SGK_KHTN_7_KNTT/page_101_img_0.png",
            "figure_label": "Hình 23.1",
            "figure_caption": "Sơ đồ quá trình quang hợp ở lá cây",
            "page": 101,
            "book": "Khoa học tự nhiên 7 (Kết nối tri thức)",
            "metadata": {
                "figure_label": "Hình 23.1",
                "figure_caption": "Sơ đồ quá trình quang hợp ở lá cây",
                "crop_text": "Ánh sáng mặt trời, Lục lạp, Nước H2O, Carbon dioxide CO2, Glucose, Oxygen O2",
                "page_number": "101",
                "pdf_filename": "SGK KHTN 7 Kết nối tri thức"
            }
        },
        {
            "image_path": "SGK_KHTN_7_KNTT/page_102_img_0.png",
            "image_url": "/images/SGK_KHTN_7_KNTT/page_102_img_0.png",
            "figure_label": "Hình 23.2",
            "figure_caption": "Mối quan hệ trao đổi chất và chuyển hóa năng lượng",
            "page": 102,
            "book": "Khoa học tự nhiên 7 (Kết nối tri thức)",
            "metadata": {
                "figure_label": "Hình 23.2",
                "figure_caption": "Mối quan hệ trao đổi chất và chuyển hóa năng lượng",
                "crop_text": "Tổng hợp chất hữu cơ, Tích lũy năng lượng",
                "page_number": "102",
                "pdf_filename": "SGK KHTN 7 Kết nối tri thức"
            }
        },
        {
            "image_path": "SGK_KHTN_7_KNTT/page_104_img_0.png",
            "image_url": "/images/SGK_KHTN_7_KNTT/page_104_img_0.png",
            "figure_label": "Hình 23.3",
            "figure_caption": "Thí nghiệm chứng minh quang hợp giải phóng oxygen",
            "page": 104,
            "book": "Khoa học tự nhiên 7 (Kết nối tri thức)",
            "metadata": {
                "figure_label": "Hình 23.3",
                "figure_caption": "Thí nghiệm chứng minh quang hợp giải phóng oxygen",
                "crop_text": "Ống nghiệm hứng bọt khí, Đèn chiếu sáng, Cành rong đuôi chó",
                "page_number": "104",
                "pdf_filename": "SGK KHTN 7 Kết nối tri thức"
            }
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

        resp_data = BIOLOGY_RESPONSE

        if path == "/api/chat/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            try:
                self.wfile.write(b'event: status\ndata: {"status": "retrieving"}\n\n')
                self.wfile.flush()
                # Delay for taking fe-ask-question screenshot while retrieving status is displayed
                time.sleep(2.0)

                self.wfile.write(b'event: status\ndata: {"status": "answering"}\n\n')
                self.wfile.flush()
                time.sleep(0.3)

                delta_payload = json.dumps({"delta": resp_data["answer_text"]}, ensure_ascii=False)
                self.wfile.write(f"event: answer_delta\ndata: {delta_payload}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(0.2)

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
            # Uniform dimensions for all chapter 3 UI screenshots
            context = browser.new_context(viewport={"width": 1205, "height": 910}, device_scale_factor=1)
            page = context.new_page()

            # -------------------------------------------------------------
            # 1. Capture fe-login.png
            # -------------------------------------------------------------
            print("\n[1/5] Capturing fe-login.png...")
            page.goto("http://localhost:3000")
            page.wait_for_load_state("networkidle")
            page.evaluate("() => localStorage.clear()")
            page.reload()
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("text=Trợ lý Khoa học tự nhiên", timeout=10000)
            page.wait_for_selector("input[type='text']", timeout=10000)
            time.sleep(1.5)  # Wait for login card entrance animation
            login_img_path = os.path.join(OUTPUT_DIR, "fe-login.png")
            page.screenshot(path=login_img_path)
            print(f"Saved: {login_img_path}")

            # -------------------------------------------------------------
            # 2. Capture fe-chatbox.png
            # -------------------------------------------------------------
            print("\n[2/5] Capturing fe-chatbox.png...")
            page.evaluate("""() => {
                localStorage.setItem('rag_user_name', 'Đăng Khoa');
                localStorage.setItem('rag_api_host', 'http://localhost:5000');
            }""")
            page.reload()
            page.wait_for_load_state("networkidle")
            page.wait_for_selector("textarea", timeout=10000)
            page.wait_for_selector("text=Chào", timeout=10000)
            time.sleep(1.5)
            chatbox_img_path = os.path.join(OUTPUT_DIR, "fe-chatbox.png")
            page.screenshot(path=chatbox_img_path)
            print(f"Saved: {chatbox_img_path}")

            # -------------------------------------------------------------
            # 3. Capture fe-ask-question.png
            # -------------------------------------------------------------
            print("\n[3/5] Capturing fe-ask-question.png...")
            bio_q = "Quá trình quang hợp ở thực vật diễn ra như thế nào và có vai trò gì?"
            page.fill("textarea", bio_q)
            time.sleep(0.3)
            page.keyboard.press("Enter")

            # During the 2.0s delay in SSE status 'retrieving', capture the loading state
            page.wait_for_selector("text=Đang tìm trong sách giáo khoa...", timeout=5000)
            time.sleep(0.5)
            ask_img_path = os.path.join(OUTPUT_DIR, "fe-ask-question.png")
            page.screenshot(path=ask_img_path)
            print(f"Saved: {ask_img_path}")

            # -------------------------------------------------------------
            # 4. Capture fe-response.png
            # -------------------------------------------------------------
            print("\n[4/5] Capturing fe-response.png...")
            page.wait_for_selector(".katex", timeout=15000)
            page.wait_for_selector("text=Nguồn trích dẫn", timeout=15000)
            page.wait_for_selector("button.group.w-36", timeout=10000)
            time.sleep(1.5)

            # Scroll to align the user message bubble at top
            page.evaluate("""() => {
                const userMsg = document.querySelector('.flex-row-reverse');
                if (userMsg) {
                    userMsg.scrollIntoView({ behavior: 'instant', block: 'start' });
                }
            }""")
            time.sleep(1.0)
            response_img_path = os.path.join(OUTPUT_DIR, "fe-response.png")
            page.screenshot(path=response_img_path)
            print(f"Saved: {response_img_path}")

            # -------------------------------------------------------------
            # 5. Capture fe-image-detail.png
            # -------------------------------------------------------------
            print("\n[5/5] Capturing fe-image-detail.png...")
            # Click on the first image thumbnail
            first_img_card = page.locator("button.group.w-36").first
            first_img_card.click()

            # Wait for modal with metadata
            page.wait_for_selector("text=Xuất xứ", timeout=10000)
            page.wait_for_selector("text=Nhãn và chú thích", timeout=10000)
            time.sleep(1.5)  # Let modal animation finish
            detail_img_path = os.path.join(OUTPUT_DIR, "fe-image-detail.png")
            page.screenshot(path=detail_img_path)
            print(f"Saved: {detail_img_path}")

            browser.close()
    finally:
        print("Cleaning up Next.js process...")
        subprocess.run(f"taskkill /F /T /PID {fe_proc.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("All screenshots successfully updated!")

if __name__ == "__main__":
    main()
