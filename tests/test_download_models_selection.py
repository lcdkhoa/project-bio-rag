"""`download_models.py` phải tải ĐÚNG thứ cần, và fail loudly khi tên sai.

Vì sao có test này: tải cả 6 model là ~15 GB. Trên Colab free đó là hàng chục
phút và gần hết disk cho một lượt chỉ chạy `--text-only` (chỉ cần bge-m3).
"""
import pytest

from src.utils.download_models import MODELS, PROFILES, select_models


def test_text_etl_profile_only_needs_the_text_embedder():
    assert select_models(profile="text-etl") == ["BAAI/bge-m3"]


def test_image_etl_profile_has_no_llm_and_no_text_embedder():
    chosen = select_models(profile="image-etl")
    assert "Qwen/Qwen2.5-3B-Instruct" not in chosen
    assert "BAAI/bge-m3" not in chosen
    assert "5CD-AI/Vintern-1B-v2" in chosen


def test_default_is_every_model():
    assert select_models() == list(MODELS)


def test_only_accepts_short_names_in_the_order_given():
    chosen = select_models(only="bge-m3,clip-vit-base-patch16")
    assert chosen == ["BAAI/bge-m3", "openai/clip-vit-base-patch16"]


def test_unknown_name_or_profile_stops_instead_of_downloading_the_wrong_thing():
    with pytest.raises(SystemExit):
        select_models(only="bge-m4")
    with pytest.raises(SystemExit):
        select_models(profile="khong-co")


def test_every_profile_lists_only_real_models():
    for name, models in PROFILES.items():
        assert set(models) <= set(MODELS), name
