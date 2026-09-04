"""LLM dùng cho sinh test + chấm (generator/judge), cấu hình qua biến môi trường.

Dùng giao thức OpenAI-compatible nên cắm được BẤT KỲ provider nào theo chuẩn này:
Xiaomi MiMo, Groq, OpenRouter, Together, vLLM tự host... Chỉ cần đặt 3 biến trong
`.env`:

    EVAL_LLM_BASE_URL = <endpoint>      # vd MiMo / Groq
    EVAL_LLM_API_KEY  = <token của bạn>
    EVAL_LLM_MODEL    = <model id>

Ví dụ cấu hình:
    # Groq
    EVAL_LLM_BASE_URL=https://api.groq.com/openai/v1
    EVAL_LLM_MODEL=qwen/qwen3.8-27b
    # Xiaomi MiMo (điền base_url + model id theo nhà cung cấp token của bạn)
    EVAL_LLM_BASE_URL=https://api.<...>/v1
    EVAL_LLM_MODEL=mimo-2.5-pro

Tùy chọn:
    EVAL_LLM_API_KEY_ENV = GROQ_API_KEY   # nếu key của bạn đã nằm ở biến tên khác
    EVAL_LLM_MODELS = <model1>,<model2>,...  # NHIỀU model cùng key/base_url, XOAY
        VÒNG khi model đang dùng bị rate-limit (429/5xx) — đo trên Groq 2026-09-01:
        mỗi model một hạn mức TPM RIÊNG (8000 token/phút/model), nên xoay sang
        model kế thay vì ngồi chờ backoff giúp lượt chấm 231 câu không bị chặn bởi
        hạn mức của một model. Có biến này thì `EVAL_LLM_MODEL` chỉ còn vai trò
        model ĐẦU DANH SÁCH; không có thì mọi hành vi giữ nguyên như một model.
"""

import os
from langchain_openai import ChatOpenAI

_DEFAULT_KEY_CANDIDATES = (
    "EVAL_LLM_API_KEY", "MIMO_API_KEY", "GROQ_API_KEY",
    "OPENROUTER_API_KEY", "OPENAI_API_KEY",
)


def _resolve_api_key() -> str:
    # Cho phép trỏ tới biến key có sẵn qua EVAL_LLM_API_KEY_ENV.
    alias = os.getenv("EVAL_LLM_API_KEY_ENV", "").strip()
    if alias and os.getenv(alias):
        return os.getenv(alias)
    for name in _DEFAULT_KEY_CANDIDATES:
        val = os.getenv(name, "").strip()
        if val:
            return val
    return ""


def is_configured() -> bool:
    has_model = bool(os.getenv("EVAL_LLM_MODEL", "").strip()
                      or os.getenv("EVAL_LLM_MODELS", "").strip())
    return bool(has_model and _resolve_api_key())


def config_help() -> str:
    return (
        "Chưa cấu hình LLM đánh giá. Thêm vào .env:\n"
        "  EVAL_LLM_BASE_URL=<endpoint OpenAI-compatible>\n"
        "  EVAL_LLM_API_KEY=<token của bạn>\n"
        "  EVAL_LLM_MODEL=<model id>\n"
        "Ví dụ Groq (free): BASE_URL=https://api.groq.com/openai/v1, MODEL=llama-3.3-70b-versatile"
    )


def _is_rate_limited(exc: Exception) -> bool:
    """429 / 5xx / quá tải — đáng để xoay sang model khác trong pool.

    KHÔNG khớp lỗi auth (401/403) hay lỗi yêu cầu sai (400): xoay model không
    cứu được hai loại đó (cùng key), và im lặng thử lại một lỗi thật là vi phạm
    nguyên tắc 5 (fail loudly).
    """
    msg = str(exc).lower()
    return any(t in msg for t in (
        "429", "rate", "500", "502", "503", "504", "overload", "capacity",
    ))


class JudgePool:
    """Xoay vòng nhiều `ChatOpenAI` client (nhiều model, CÙNG key/base_url).

    `.invoke()` cùng chữ ký với `ChatOpenAI.invoke()` nên gọi thay thế được ở
    mọi chỗ đang dùng `get_eval_llm()` — không đổi code gọi. Khi model đang
    active bị rate-limit, xoay sang model kế NGAY (không sleep, vì hạn mức là
    theo TỪNG model) rồi thử tiếp; hết một vòng cả pool mà vẫn lỗi thì ném lỗi
    cuối cùng lên cho lớp gọi (run_eval.py đã có backoff riêng ở lớp đó).
    """

    def __init__(self, clients):
        if not clients:
            raise ValueError("JudgePool cần ít nhất một (tên model, client)")
        self._clients = list(clients)
        self._idx = 0

    def force_rotate(self):
        """Xoay sang model kế BẤT KỂ lý do — dùng khi lỗi không đến từ chính
        lệnh gọi API (vd JSON hỏng cú pháp ở lớp gọi), nên `.invoke()` không tự
        biết mà xoay. Cần thiết vì `temperature=0.0` khiến CÙNG model trả lại
        NGUYÊN VĂN cùng một JSON hỏng nếu thử lại mà không đổi model."""
        if len(self._clients) > 1:
            self._idx = (self._idx + 1) % len(self._clients)

    def invoke(self, prompt, **kwargs):
        last_exc = None
        n = len(self._clients)
        for _ in range(n):
            name, client = self._clients[self._idx]
            try:
                return client.invoke(prompt, **kwargs)
            except Exception as exc:  # noqa: BLE001 - phân loại lại ngay dưới
                last_exc = exc
                if n > 1 and _is_rate_limited(exc):
                    print(f"[eval_llm] {name} rate-limited, xoay sang model kế trong pool")
                    self._idx = (self._idx + 1) % n
                    continue
                raise
        raise last_exc


def get_eval_llm(temperature: float = 0.0, **kwargs):
    """Tạo client LLM đánh giá từ env. Báo lỗi rõ ràng nếu thiếu cấu hình.

    Trả `ChatOpenAI` đơn khi chỉ có `EVAL_LLM_MODEL`; trả `JudgePool` (nhiều
    model, cùng key/base_url) khi có `EVAL_LLM_MODELS` (phân tách bằng dấu
    phẩy) — xem docstring module.
    """
    api_key = _resolve_api_key()
    base_url = os.getenv("EVAL_LLM_BASE_URL", "").strip() or None
    models_csv = os.getenv("EVAL_LLM_MODELS", "").strip()
    models = [m.strip() for m in models_csv.split(",") if m.strip()] if models_csv else []
    if not models:
        single = os.getenv("EVAL_LLM_MODEL", "").strip()
        models = [single] if single else []

    if not models or not api_key:
        raise RuntimeError(config_help())

    clients = []
    for model in models:
        print(f"[eval_llm] model={model} base_url={base_url or 'default(openai)'}")
        clients.append((model, ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            timeout=60,
            max_retries=2,
            **kwargs,
        )))

    if len(clients) == 1:
        return clients[0][1]
    return JudgePool(clients)
