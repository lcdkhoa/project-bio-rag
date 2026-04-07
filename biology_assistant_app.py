import os
import re
import torch
import gradio as gr
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings, HuggingFacePipeline
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

DEFAULT_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "biology_db_rag")
PERSIST_DIR = os.environ.get("BIOLOGY_RAG_DB_DIR", DEFAULT_PERSIST_DIR)

# 2. KHỞI TẠO EMBEDDING & KẾT NỐI VECTOR DB
print("Đang kết nối Vector Database...")
embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
db = Chroma(
    collection_name="biology_docs",
    embedding_function=embedding_model,
    persist_directory=PERSIST_DIR,
)
retriever = db.as_retriever(search_type="similarity", search_kwargs={"k": 4})
print(f"✅ Đã kết nối DB! Hiện có {db._collection.count()} chunks.")

# 3. TẢI MÔ HÌNH LLM (QWEN)
print("Đang tải não bộ LLM (Qwen2.5-3B-Instruct)...")
model_name = "Qwen/Qwen2.5-3B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto",
    low_cpu_mem_usage=True
)

model_pipeline = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=1000,
    pad_token_id=tokenizer.eos_token_id,
    do_sample=False, # Tắt tính năng sáng tạo, ép mô hình "nói có sách mách có chứng"
)
llm = HuggingFacePipeline(pipeline=model_pipeline)
print("✅ LLM đã sẵn sàng!")

# 4. XÂY DỰNG PROMPT CHUẨN CHATML CỦA QWEN VÀ PARSER
class FocusedAnswerParser(StrOutputParser):
    def parse(self, text: str) -> str:
        # Cắt lấy phần sau tag assistant nếu có
        if "<|im_start|>assistant" in text:
            text = text.split("<|im_start|>assistant")[-1]

        text = text.replace("<|im_end|>", "").strip()
        text = re.sub(r'^\s*[\-\*]\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n+', ' ', text)
        lines = [line.strip() for line in text.split('.') if line.strip() and len(line.strip()) > 5]
        return '. '.join(lines[:6]) + ('.' if lines else '')

# Sử dụng cú pháp ChatML gốc để ép khuôn ngôn ngữ và hành vi
prompt_template = """<|im_start|>system
Bạn là trợ lý AI môn Sinh học THCS. Bạn PHẢI trả lời hoàn toàn bằng TIẾNG VIỆT.<|im_end|>
<|im_start|>user
[TÀI LIỆU SÁCH GIÁO KHOA]:
{context}

[CÂU HỎI]:
{question}

[QUY TẮC NGHIÊM NGẶT]:
1. CHỈ dùng thông tin trong tài liệu trên. KHÔNG tự suy diễn.
2. Nếu tài liệu không chứa câu trả lời, hãy trả lời ĐÚNG CÂU SAU: "Thông tin này không được đề cập trong sách giáo khoa."<|im_end|>
<|im_start|>assistant
"""
prompt = PromptTemplate.from_template(prompt_template)
rag_chain = prompt | llm | FocusedAnswerParser()

# 5. HÀM WRAPPER: KẾT HỢP RETRIEVE, INFER VÀ TRÍCH XUẤT NGUỒN
def answer_biology_question(question):
    try:
        # Tự gọi retriever để lấy chunks kèm metadata
        docs = retriever.invoke(question)
        if not docs:
            return "Hệ thống chưa tìm thấy tài liệu nào liên quan đến câu hỏi này."

        # Trích xuất nguồn (Loại bỏ các nguồn trùng lặp)
        context_texts = []
        citations = set()
        for doc in docs:
            context_texts.append(doc.page_content)
            source_file = doc.metadata.get('source', 'Sách Giáo Khoa')
            page_num = doc.metadata.get('page', 'Không rõ')
            citations.add(f"📖 {source_file} (Trang {page_num})")

        # Nối text đưa cho LLM đọc
        context_str = "\n\n".join(context_texts)

        # Đưa vào RAG Chain
        answer = rag_chain.invoke({"context": context_str, "question": question})

        # Nếu mô hình thú nhận không có thông tin thì không in nguồn
        if "không được đề cập" in answer.lower():
            return answer

        # Đính kèm nguồn vào cuối câu trả lời
        final_output = f"{answer}\n\n📚 Thông tin được tham khảo từ:\n" + "\n".join(citations)
        return final_output

    except Exception as e:
        return f"Lỗi hệ thống: {str(e)}"

# 6. XÂY DỰNG GIAO DIỆN WEB (GRADIO)
with gr.Blocks(title="Trợ lý ảo Sinh Học THCS", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🧬 Trợ Lý Ảo Hỗ Trợ Học Tập Môn Sinh Học")
    gr.Markdown("*Hệ thống AI RAG xây dựng dựa trên Sách Giáo Khoa Sinh học THCS.*")

    with gr.Row():
        with gr.Column(scale=1):
            question_input = gr.Textbox(
                label="Câu hỏi của bạn",
                placeholder="Ví dụ: Tế bào là gì? Vì sao nói tế bào là đơn vị cơ bản của sự sống?",
                lines=4
            )
            submit_btn = gr.Button("Gửi câu hỏi", variant="primary")

        with gr.Column(scale=2):
            answer_output = gr.Textbox(
                label="Trợ lý AI trả lời",
                lines=8,
                interactive=False
            )

    submit_btn.click(
        fn=answer_biology_question,
        inputs=question_input,
        outputs=answer_output
    )

print("\n🚀 Đang khởi chạy giao diện web...")
if __name__ == "__main__":
    # share=True cần thiết lập tunnel; để chạy local ổn định, dùng share=False.
    demo.launch(share=False)