# Cài đặt các thư viện chính cho mô hình ngôn ngữ, embedding và RAG
!pip install -q torch>=2.0.0 transformers>=4.40.0 accelerate>=0.30.0 huggingface-hub>=0.23.0
!pip install -q sentence-transformers>=2.7.0 langchain>=0.2.0 langchain-core>=0.2.0 langchain-community>=0.1.0 langchain-text-splitters>=0.2.0
!pip install -q chromadb>=0.5.0 langchain-chroma>=0.2.0 pypdf>=4.2.0 langchain-huggingface wget

import torch
import langchain
import chromadb
from transformers import pipeline

print("Import thành công! Thư viện đã sẵn sàng.")

import os
import sys

PROJECT_ROOT = "/content/rag_biology"

# Đặt token Hugging Face của em vào đây để tải các mô hình (ví dụ: Qwen)
os.environ["HF_TOKEN"] = "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"

# Tạo thư mục cho sách giáo khoa Sinh học và phân luồng mã nguồn
os.makedirs(os.path.join(PROJECT_ROOT, "data_source", "biology_textbooks"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, "src", "base"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, "src", "rag"), exist_ok=True)

os.chdir(PROJECT_ROOT)

# Thêm PROJECT_ROOT vào sys.path để import module dễ dàng
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

import re
import unicodedata

def clean_vietnamese_text(text: str) -> str:
    # Chuẩn hóa Unicode về dạng NFC cho tiếng Việt [cite: 687]
    text = unicodedata.normalize('NFC', text)

    # Loại bỏ các ký tự điều khiển (trừ tab và xuống dòng) [cite: 689-693]
    text = "".join(
        char for char in text
        if not unicodedata.category(char).startswith('C') or char in '\n\t'
    )

    # Xử lý khoảng trắng thừa và dòng trống [cite: 703-705]
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)

    return text.strip()

import glob
from tqdm import tqdm
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

class SimpleLoader:
    def load_pdf(self, pdf_file: str):
        # Tải PDF và trích xuất hình ảnh (theo cấu hình của tài liệu AIO2025) [cite: 721]
        docs = PyPDFLoader(pdf_file, extract_images=True).load()
        for doc in docs:
            # Gọi hàm làm sạch tiếng Việt ở Bước 3
            doc.page_content = clean_vietnamese_text(doc.page_content)
        return docs

    def load_dir(self, dir_path: str):
        pdf_files = glob.glob(f"{dir_path}/*.pdf")
        if not pdf_files:
            raise ValueError(f"Không tìm thấy file PDF nào trong {dir_path}. Em kiểm tra lại xem đã upload thành công chưa nhé!")

        all_docs = []
        for pdf_file in tqdm(pdf_files, desc="Đang tải sách giáo khoa Sinh học"):
            try:
                all_docs.extend(self.load_pdf(pdf_file))
            except Exception as e:
                print(f"Lỗi khi tải file {pdf_file}: {e}")
                pass
        return all_docs

class TextSplitter:
    def __init__(self, chunk_size: int = 400, chunk_overlap: int = 120):
        # Sử dụng cấu hình chia cắt đệ quy tối ưu cho tiếng Việt [cite: 757-775]
        self.splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", " ", ""],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap, # Giữ lại 120 ký tự trùng lặp làm cầu nối ngữ cảnh [cite: 182]
            length_function=len,
        )

    def split(self, documents):
        return self.splitter.split_documents(documents)

# Cài đặt công cụ chuyển PDF thành ảnh và Tesseract OCR (kèm tiếng Việt) ở mức OS
!apt-get update
!apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-vie

# Cài đặt thư viện Python để giao tiếp với Tesseract
!pip install -q pytesseract pdf2image

import glob
from tqdm import tqdm
from pdf2image import convert_from_path
import pytesseract
from langchain_core.documents import Document

class RobustOCRLoader:
    def load_pdf(self, pdf_file: str):
        docs = []
        try:
            # Bước 1: Chuyển toàn bộ trang PDF thành danh sách hình ảnh
            images = convert_from_path(pdf_file)

            # Bước 2: OCR từng ảnh
            for i, img in enumerate(images):
                # Ép Tesseract dùng model tiếng Việt ('vie')
                raw_text = pytesseract.image_to_string(img, lang='vie')

                # Làm sạch văn bản
                cleaned_text = clean_vietnamese_text(raw_text)

                # Chỉ lưu những trang thực sự có chữ
                if cleaned_text and len(cleaned_text) > 10:
                    doc = Document(
                        page_content=cleaned_text,
                        metadata={"source": pdf_file, "page": i + 1}
                    )
                    docs.append(doc)
        except Exception as e:
            print(f"Lỗi khi OCR file {pdf_file}: {e}")

        return docs

    def load_dir(self, dir_path: str):
        pdf_files = glob.glob(f"{dir_path}/*.pdf")
        all_docs = []
        # Chạy OCR sẽ khá lâu, thanh tiến trình tqdm sẽ giúp em theo dõi
        for pdf_file in tqdm(pdf_files, desc="Đang OCR sách giáo khoa Sinh học"):
            all_docs.extend(self.load_pdf(pdf_file))
        return all_docs

!pip install -q rapidocr-onnxruntime

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

class VectorDB:
    def __init__(
        self,
        documents=None,
        embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        collection_name: str = "biology_docs",
        persist_dir: str = "/content/rag_biology/chroma_data",
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        # Khởi tạo mô hình embedding đa ngôn ngữ [cite: 815-816]
        self.embedding = HuggingFaceEmbeddings(model_name=embedding_model)
        self.db = self._build_db(documents)

    def _build_db(self, documents):
        if documents is None or len(documents) == 0:
            # Tải DB đã có sẵn [cite: 839-841]
            db = Chroma(
                collection_name=self.collection_name,
                embedding_function=self.embedding,
                persist_directory=self.persist_dir,
            )
        else:
            # Tạo DB mới từ documents [cite: 842-847]
            db = Chroma.from_documents(
                documents=documents,
                embedding=self.embedding,
                collection_name=self.collection_name,
                persist_directory=self.persist_dir,
            )
        return db

    def get_retriever(self, search_kwargs: dict = None):
        if search_kwargs is None:
            search_kwargs = {"k": 3} # Lấy 3 đoạn văn bản liên quan nhất
        return self.db.as_retriever(
            search_type="similarity",
            search_kwargs=search_kwargs,
        )

# CHẠY THỬ: Đưa các chunk test của em vào Vector DB
print("Đang khởi tạo Vector Database và embedding các chunks...")
vdb = VectorDB(documents=test_split_docs)
retriever = vdb.get_retriever()
print("✅ Vector Database đã sẵn sàng!")

import torch
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
from langchain_huggingface import HuggingFacePipeline

def get_hf_llm(
    model_name: str = "Qwen/Qwen2.5-3B-Instruct",
    temperature: float = 0.1, # Đặt thấp để mô hình bám sát sách giáo khoa, không bịa đặt [cite: 1239-1243]
    max_new_tokens: int = 500,
    **kwargs
):
    print(f"Đang tải mô hình {model_name}...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16, # Dùng float16 để tiết kiệm VRAM GPU [cite: 893-895]
        device_map="auto",
        low_cpu_mem_usage=True
    )
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    model_pipeline = pipeline(
        "text-generation",
        model=model,
        tokenizer=tokenizer,
        temperature=temperature,
        max_new_tokens=max_new_tokens,
        pad_token_id=tokenizer.eos_token_id,
        do_sample=True,
        top_p=0.75
    )

    # Đóng gói vào LangChain [cite: 932-936]
    llm = HuggingFacePipeline(pipeline=model_pipeline, model_kwargs=kwargs)
    return llm

# Khởi tạo LLM
llm = get_hf_llm()
print("✅ Mô hình LLM đã sẵn sàng!")

import re
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

class FocusedAnswerParser(StrOutputParser):
    def parse(self, text: str) -> str:
        text = text.strip()
        # Cắt lấy phần sau chữ [TRẢ LỜI] [cite: 948-955]
        if "[TRẢ LỜI]:" in text:
            answer = text.split("[TRẢ LỜI]:")[-1].strip()
        else:
            answer = text

        # Làm sạch các ký tự thừa [cite: 963-964]
        answer = re.sub(r'^\s*[\-\*]\s*', '', answer, flags=re.MULTILINE)
        answer = re.sub(r'\n+', ' ', answer)

        # Giới hạn lấy tối đa 5 câu đầu tiên cho gãy gọn [cite: 965-967]
        lines = [line.strip() for line in answer.split('.') if line.strip() and len(line.strip()) > 5]
        return '. '.join(lines[:5]) + ('.' if lines else '')

class BiologyRAG:
    def __init__(self, llm):
        self.llm = llm
        # Prompt được thiết kế khắt khe để tránh bịa đặt thông tin [cite: 976-991]
        self.prompt = PromptTemplate.from_template("""
        Bạn là trợ lý AI thông minh hỗ trợ dạy và học môn Sinh học.

        [TÀI LIỆU SÁCH GIÁO KHOA]:
        {context}

        [CÂU HỎI CỦA HỌC SINH]:
        {question}

        Hãy trả lời dựa trên tài liệu. Nếu tài liệu không có thông tin, nói rõ "Không có thông tin".
        Trả lời đầy đủ thông tin (3-5 câu chi tiết), không thêm bất kỳ chi tiết nào ngoài tài liệu.

        [TRẢ LỜI]: """)
        self.answer_parser = FocusedAnswerParser()

    def get_chain(self, retriever):
        def format_docs(docs):
            formatted = []
            seen = set()
            for doc in docs:
                content = doc.page_content.strip()
                # Loại bỏ đoạn ngắn và chống trùng lặp ngữ cảnh [cite: 1001-1009]
                if content and len(content) > 40 and content not in seen:
                    formatted.append(content)
                    seen.add(content)
            return "\n\n".join(formatted)

        # Kết nối pipeline bằng LCEL (LangChain Expression Language) [cite: 1018-1029]
        rag_chain = (
            {"context": retriever | format_docs, "question": RunnablePassthrough()}
            | self.prompt
            | self.llm
            | self.answer_parser
        )
        return rag_chain

# Khởi tạo RAG Chain
rag = BiologyRAG(llm)
rag_chain = rag.get_chain(retriever)

def ask_biology_assistant(question: str) -> str:
    print(f"🧐 Học sinh hỏi: {question}")
    print("🤖 Đang suy nghĩ và tra cứu SGK...")
    try:
        answer = rag_chain.invoke(question)
        print(f"✅ Trả lời: {answer}\n")
        return answer
    except Exception as e:
        print(f"❌ Lỗi: {str(e)}")
        return "Xin lỗi, đã có lỗi xảy ra."

# Gọi hàm test thử
response = ask_biology_assistant("Hãy cho biết sếp Tú có đẹp trai không?")

"""#############################################################################
Real Task Now
"""

# Cài đặt công cụ hệ thống và thư viện OCR
!apt-get update
!apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-vie
!pip install -q pytesseract pdf2image langchain-chroma langchain-huggingface sentence-transformers

from google.colab import drive
import os

drive.mount('/content/drive')

DATA_DIR = "/content/rag_biology/data_source/biology_textbooks"
PERSIST_DIR = "/content/drive/MyDrive/biology_rag_db"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PERSIST_DIR, exist_ok=True)

print("✅ Đã kết nối Google Drive và sẵn sàng!")

import os
import glob
import sys
import re
import unicodedata
from tqdm import tqdm
from pdf2image import convert_from_path
import pytesseract
from google.colab import drive
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# 1. MOUNT DRIVE & KHAI BÁO ĐƯỜNG DẪN
drive.mount('/content/drive')

DATA_DIR = "/content/rag_biology/data_source/biology_textbooks" # Thư mục chứa PDF
PERSIST_DIR = "/content/drive/MyDrive/biology_db_rag" # Thư mục lưu DB vĩnh viễn
TRACKING_FILE = os.path.join(PERSIST_DIR, "processed_files.txt") # File lưu vết

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PERSIST_DIR, exist_ok=True)

# 2. HÀM QUẢN LÝ CHECKPOINT (TRACKING)
def get_processed_files():
    """Đọc danh sách các file đã xử lý thành công từ file log"""
    if not os.path.exists(TRACKING_FILE):
        return set()
    with open(TRACKING_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def mark_file_as_processed(filename):
    """Ghi nhận file đã hoàn tất vào log"""
    with open(TRACKING_FILE, "a", encoding="utf-8") as f:
        f.write(f"{filename}\n")

# 3. HÀM LÀM SẠCH VĂN BẢN
def clean_vietnamese_text(text: str) -> str:
    text = unicodedata.normalize('NFC', text)
    text = "".join(
        char for char in text
        if not unicodedata.category(char).startswith('C') or char in '\n\t'
    )
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()

# 4. KHỞI TẠO SPLITTER VÀ EMBEDDING
text_splitter = RecursiveCharacterTextSplitter(
    separators=["\n\n", "\n", " ", ""],
    chunk_size=400,
    chunk_overlap=120,
    length_function=len,
)
print("Đang tải mô hình Embedding...")
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# 5. KẾT NỐI VECTOR DATABASE (TRÊN DRIVE) VÀ KIỂM TRA
print("Đang kết nối Vector Database trên Google Drive...")
try:
    db = Chroma(
        collection_name="biology_docs",
        embedding_function=embedding_model,
        persist_directory=PERSIST_DIR,
    )

    # "Ping" thử database bằng cách đếm số lượng vector đang có
    current_docs = db._collection.count()
    print(f"✅ Kết nối VectorDB thành công! Hiện đang có {current_docs} chunks trong collection.")

except Exception as e:
    print(f"❌ FATAL ERROR: Không thể kết nối hoặc khởi tạo Vector Database.")
    print(f"Chi tiết lỗi: {e}")
    print("⚠️ Vui lòng kiểm tra lại xem Google Drive đã được mount thành công chưa, hoặc đường dẫn PERSIST_DIR có hợp lệ không.")
    # Ngắt toàn bộ pipeline để tránh việc OCR xong nhưng không có chỗ lưu
    sys.exit("Dừng script do lỗi Database.")

# 6. VÒNG LẶP XỬ LÝ CHÍNH (ETL) VỚI RESUME CAPABILITY
pdf_files = glob.glob(f"{DATA_DIR}/*.pdf")
processed_files = get_processed_files()

if not pdf_files:
    print("❌ Không tìm thấy file PDF nào. Vui lòng upload lại sách vào DATA_DIR.")
else:
    print(f"📊 Tổng số sách trong thư mục: {len(pdf_files)}")
    print(f"✅ Đã xử lý thành công trước đó: {len(processed_files)} cuốn")

    files_to_process = [f for f in pdf_files if os.path.basename(f) not in processed_files]
    print(f"🚀 Cần xử lý tiếp: {len(files_to_process)} cuốn\n")

    for pdf_file in files_to_process:
        filename = os.path.basename(pdf_file)
        print(f"🔄 Bắt đầu xử lý: {filename}")

        try:
            # Chuyển PDF thành ảnh
            images = convert_from_path(pdf_file)
            file_docs = []

            # OCR từng trang
            for i, img in enumerate(tqdm(images, desc=f"OCR {filename}")):
                raw_text = pytesseract.image_to_string(img, lang='vie')
                cleaned_text = clean_vietnamese_text(raw_text)

                if cleaned_text and len(cleaned_text) > 10:
                    doc = Document(
                        page_content=cleaned_text,
                        metadata={"source": filename, "page": i + 1}
                    )
                    file_docs.append(doc)

            if file_docs:
                # Cắt chunk cho cuốn sách này
                split_docs = text_splitter.split_documents(file_docs)
                print(f"👉 Đã chia thành {len(split_docs)} chunks. Đang lưu vào ChromaDB...")

                # Lưu vào ChromaDB trên Drive
                db.add_documents(split_docs)

                # Cập nhật Checkpoint: Đánh dấu đã hoàn thành
                mark_file_as_processed(filename)
                print(f"✅ Đã lưu DB và ghi log thành công cuốn: {filename}\n")
            else:
                print(f"⚠️ Cuốn {filename} không trích xuất được chữ nào. (Sẽ đánh dấu hoàn thành để bỏ qua lần sau)")
                mark_file_as_processed(filename)

        except Exception as e:
            print(f"❌ Lỗi khi xử lý cuốn {filename}: {e}")
            print("⚠️ Quá trình bị gián đoạn tại đây. Cuốn này chưa được lưu log.")
            # Bỏ qua cuốn bị lỗi và có thể chuyển sang cuốn tiếp theo (hoặc ngưng tùy ý)
            continue

print("\n🎉 HOÀN TẤT TOÀN BỘ QUÁ TRÌNH DATA INGESTION!")