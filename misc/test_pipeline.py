"""tests/test_pipeline.py — full integration tests (LLM mocked)."""
import json
from unittest.mock import MagicMock
import pytest
from src.llm.engine import RAGOutput
from src.pipeline.pipeline import PipelineResult, RAGPipeline

ARTICLE = """
The Rise of Large Language Models in 2024
By Dr. Emily Chen | March 10, 2024

Large language models have fundamentally changed AI research. Models like GPT-4
and Claude demonstrate unprecedented capabilities in reasoning and coding.
Dr. Emily Chen from MIT has published extensive research on alignment.
Key finding: models above 100B parameters exhibit qualitatively different reasoning.
Commercial applications in healthcare, legal, and finance are accelerating.
"""

MOCK_OUTPUT = RAGOutput(
    title    = "The Rise of Large Language Models in 2024",
    author   = "Dr. Emily Chen",
    date     = "2024-03-10",
    summary  = "LLMs transform AI research with emergent reasoning at scale.",
    keywords = ["LLMs", "GPT-4", "alignment", "AI research", "emergent behavior"],
)


def _pipeline(tmp_path) -> RAGPipeline:
    """Pipeline with temp index dir and mocked LLM."""
    p = RAGPipeline()
    p.store = type(p.store)(index_dir=tmp_path, index_name="t", dim=384)
    p.llm   = MagicMock()
    p.llm.extract.return_value = MOCK_OUTPUT
    return p


class TestRAGPipeline:

    def test_run_returns_pipeline_result(self, tmp_path):
        r = _pipeline(tmp_path).run(ARTICLE)
        assert isinstance(r, PipelineResult)

    def test_output_has_all_schema_keys(self, tmp_path):
        out = _pipeline(tmp_path).run(ARTICLE).output
        assert out.title != ""
        assert out.author != ""
        assert isinstance(out.keywords, list)

    def test_to_json_is_valid(self, tmp_path):
        j = _pipeline(tmp_path).run(ARTICLE).to_json()
        d = json.loads(j)
        for key in ("title", "author", "date", "summary", "keywords"):
            assert key in d
        assert isinstance(d["keywords"], list)

    def test_index_increases_store_size(self, tmp_path):
        p = _pipeline(tmp_path)
        assert p.store.is_empty
        p.index(ARTICLE)
        assert p.store.size > 0

    def test_multiple_index_accumulates(self, tmp_path):
        p = _pipeline(tmp_path)
        p.index("First document about machine learning AI systems.")
        s1 = p.store.size
        p.index("Second document about natural language processing techniques.")
        assert p.store.size > s1

    def test_batch_method(self, tmp_path):
        p  = _pipeline(tmp_path)
        texts = [
            "Machine learning in healthcare applications.",
            "Deep learning for computer vision and object detection.",
        ]
        r = p.batch(texts, "What topics are covered?")
        assert isinstance(r, PipelineResult)

    def test_stats_populated(self, tmp_path):
        s = _pipeline(tmp_path).run(ARTICLE).stats
        assert s.chunks > 0
        assert s.embed_ms > 0

    def test_reset_clears_index(self, tmp_path):
        p = _pipeline(tmp_path)
        p.index(ARTICLE)
        p.reset()
        assert p.store.is_empty

    def test_save_load_index(self, tmp_path):
        p = _pipeline(tmp_path)
        p.index(ARTICLE)
        size = p.store.size
        p.save()
        p.reset()
        assert p.load()
        assert p.store.size == size

    def test_empty_text_returns_empty_output(self, tmp_path):
        p      = _pipeline(tmp_path)
        p.llm.extract.return_value = RAGOutput()
        r = p.run("")
        assert isinstance(r, PipelineResult)
        assert r.stats.chunks == 0

    def test_hits_in_result(self, tmp_path):
        r = _pipeline(tmp_path).run(ARTICLE)
        assert len(r.hits) > 0


class TestRAGOutput:

    def test_to_dict_keys(self):
        out = RAGOutput(title="T", author="A", date="2024-01-01",
                        summary="S", keywords=["k1"])
        d   = out.to_dict()
        assert set(d) == {"title", "author", "date", "summary", "keywords"}

    def test_to_json_roundtrip(self):
        out = RAGOutput(title="AI", author="Dr. X", date="2024-06-15",
                        summary="AI summary.", keywords=["AI", "ML"])
        d   = json.loads(out.to_json())
        assert d["title"]    == "AI"
        assert d["date"]     == "2024-06-15"
        assert d["keywords"] == ["AI", "ML"]

    def test_defaults(self):
        out = RAGOutput()
        assert out.title    == "Unknown"
        assert out.keywords == []
