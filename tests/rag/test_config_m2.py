import importlib


def test_m2_config_defaults(monkeypatch):
    # Clear any env overrides so we assert the coded defaults.
    for key in ["EMBEDDING_MODEL", "RERANK_ENABLED", "RERANK_MODEL",
                "RERANK_FETCH_K", "RERANK_SCORE_MIN", "IMAGE_RERANK_ENABLED",
                "IMAGE_RERANK_TOP_N", "IMAGE_RERANK_WEIGHT"]:
        monkeypatch.delenv(key, raising=False)
    import src.config as cfg
    importlib.reload(cfg)

    assert cfg.EMBEDDING_MODEL == "BAAI/bge-m3"
    assert cfg.RERANK_ENABLED is True
    assert cfg.RERANK_MODEL == "BAAI/bge-reranker-v2-m3"
    assert cfg.RERANK_FETCH_K == 20
    assert cfg.RERANK_SCORE_MIN == 0.2
    assert cfg.IMAGE_RERANK_ENABLED is True
    assert cfg.IMAGE_RERANK_TOP_N == 12
    assert cfg.IMAGE_RERANK_WEIGHT == 0.25
