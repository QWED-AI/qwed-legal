"""Tests for SACProcessor — Summary-Augmented Chunking."""

import pytest

from qwed_legal.rag.sac_processor import SACProcessor


class MockLLM:
    """Mock LLM client that returns a fixed summary."""

    def __init__(self, response="NDA between Acme Corp and Beta Inc for mutual confidentiality"):
        self.response = response
        self.call_count = 0

    def generate(self, prompt: str) -> str:
        self.call_count += 1
        return self.response


class TestSACProcessor:
    """Test suite for SACProcessor."""

    def setup_method(self):
        self.llm = MockLLM()
        self.processor = SACProcessor(llm_client=self.llm)

    # ------------------------------------------------------------------ #
    # Basic augmentation
    # ------------------------------------------------------------------ #

    def test_generate_sac_chunks_basic(self):
        doc = "This is a Non-Disclosure Agreement between Acme Corp and Beta Inc."
        chunks = ["Clause 1: Confidentiality", "Clause 2: Term", "Clause 3: Remedies"]
        result = self.processor.generate_sac_chunks(doc, chunks)

        assert len(result) == 3
        assert "DOCUMENT CONTEXT" in result[0]
        assert "CHUNK CONTENT" in result[0]
        assert "Clause 1: Confidentiality" in result[0]
        assert "[1/3]" in result[0]
        assert "[2/3]" in result[1]
        assert "[3/3]" in result[2]

    def test_generate_sac_chunks_preserves_order(self):
        chunks = ["first", "second", "third"]
        result = self.processor.generate_sac_chunks("doc text", chunks)
        assert "first" in result[0]
        assert "second" in result[1]
        assert "third" in result[2]

    def test_empty_chunks_returns_empty(self):
        result = self.processor.generate_sac_chunks("document text", [])
        assert result == []

    def test_single_chunk(self):
        result = self.processor.generate_sac_chunks("doc", ["only chunk"])
        assert len(result) == 1
        assert "[1/1]" in result[0]

    # ------------------------------------------------------------------ #
    # Document ID
    # ------------------------------------------------------------------ #

    def test_custom_document_id(self):
        result = self.processor.generate_sac_chunks(
            "doc text", ["chunk"], document_id="NDA-2026-001"
        )
        assert "NDA-2026-001" in result[0]

    def test_auto_generated_document_id(self):
        result = self.processor.generate_sac_chunks("doc text", ["chunk"])
        assert "doc-" in result[0]

    # ------------------------------------------------------------------ #
    # Fingerprint only
    # ------------------------------------------------------------------ #

    def test_generate_fingerprint_only(self):
        summary = self.processor.generate_fingerprint_only("some legal text")
        assert summary == "NDA between Acme Corp and Beta Inc for mutual confidentiality"
        assert self.llm.call_count == 1

    # ------------------------------------------------------------------ #
    # LLM called once per generate
    # ------------------------------------------------------------------ #

    def test_llm_called_once_per_generate(self):
        self.processor.generate_sac_chunks("doc", ["a", "b", "c"])
        assert self.llm.call_count == 1

    # ------------------------------------------------------------------ #
    # Summary truncation
    # ------------------------------------------------------------------ #

    def test_long_summary_truncated(self):
        long_response = "A" * 500
        llm = MockLLM(response=long_response)
        proc = SACProcessor(llm_client=llm, target_summary_length=150)
        summary = proc.generate_fingerprint_only("doc")
        assert len(summary) <= 151  # 150 + ellipsis char

    def test_short_summary_not_truncated(self):
        short = "Short NDA summary"
        llm = MockLLM(response=short)
        proc = SACProcessor(llm_client=llm)
        assert proc.generate_fingerprint_only("doc") == short

    # ------------------------------------------------------------------ #
    # Defensive: None / empty LLM returns (Sentry bug fix)
    # ------------------------------------------------------------------ #

    def test_none_llm_return_fallback(self):
        llm = MockLLM(response=None)
        proc = SACProcessor(llm_client=llm)
        summary = proc.generate_fingerprint_only("some document")
        assert summary.startswith("doc-")

    def test_empty_llm_return_fallback(self):
        llm = MockLLM(response="")
        proc = SACProcessor(llm_client=llm)
        summary = proc.generate_fingerprint_only("some document")
        assert summary.startswith("doc-")

    def test_whitespace_llm_return_fallback(self):
        llm = MockLLM(response="   \n\t  ")
        proc = SACProcessor(llm_client=llm)
        summary = proc.generate_fingerprint_only("some document")
        assert summary.startswith("doc-")

    # ------------------------------------------------------------------ #
    # Parameter validation
    # ------------------------------------------------------------------ #

    def test_preview_chars_clamped(self):
        proc = SACProcessor(llm_client=self.llm, preview_chars=-10)
        assert proc._preview_chars == 1

    def test_preview_chars_zero_clamped(self):
        proc = SACProcessor(llm_client=self.llm, preview_chars=0)
        assert proc._preview_chars == 1

    def test_target_length_clamped_min(self):
        proc = SACProcessor(llm_client=self.llm, target_summary_length=10)
        assert proc._target_length == SACProcessor.MIN_SUMMARY_LENGTH

    def test_target_length_clamped_max(self):
        proc = SACProcessor(llm_client=self.llm, target_summary_length=9999)
        assert proc._target_length == SACProcessor.MAX_SUMMARY_LENGTH

    # ------------------------------------------------------------------ #
    # Hash ID
    # ------------------------------------------------------------------ #

    def test_hash_id_deterministic(self):
        h1 = SACProcessor._hash_id("same text")
        h2 = SACProcessor._hash_id("same text")
        assert h1 == h2
        assert h1.startswith("doc-")

    def test_hash_id_different_for_different_text(self):
        h1 = SACProcessor._hash_id("text A")
        h2 = SACProcessor._hash_id("text B")
        assert h1 != h2
