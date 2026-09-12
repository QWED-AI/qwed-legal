"""
Summary-Augmented Chunking (SAC) Processor for Legal RAG.

Prevents Document-Level Retrieval Mismatch (DRM) in legal databases.
Standard chunking causes >95% DRM in NDAs and similar contracts because
all legal documents share boilerplate structures that are nearly identical
at the chunk level. SAC fixes this by prepending a concise global
"document fingerprint" to every chunk before embedding.

Key insight: Generic (automated) summaries outperform expert-guided ones
for retrieval purposes, because they capture the distinguishing features
of each document rather than imposing a uniform structure.

Source: "Towards Reliable Retrieval in RAG Systems for Large Legal Datasets".
"""

import hashlib
import re
from typing import List, Optional, Protocol


class LLMClient(Protocol):
    """Protocol for any LLM client that can generate text."""

    def generate(self, prompt: str) -> str: ...


class SACProcessor:
    """
    Implements Summary-Augmented Chunking (SAC) to prevent
    Document-Level Retrieval Mismatch (DRM) in legal databases.

    The processor:
      1. Generates a concise (~150-char) *document fingerprint* from the
         full text using an LLM.
      2. Prepends that fingerprint to every chunk, preserving global
         context that is lost by naive splitting.

    Trust model (issue #42): the fingerprint is **LLM output** — a
    compromised or malfunctioning summarizer must not poison retrieval.
    Every augmented chunk therefore (a) labels the summary as
    AI-GENERATED and UNTRUSTED, (b) carries the deterministic document
    hash alongside it, and (c) receives a sanitized summary (newlines
    and control characters stripped, internal chunk/context markers
    removed) so the fingerprint cannot forge chunk structure or inject
    new chunk boundaries.

    Usage::

        from qwed_legal.rag.sac_processor import SACProcessor

        sac = SACProcessor(llm_client=my_llm)
        chunks = naive_split(contract_text)
        augmented = sac.generate_sac_chunks(contract_text, chunks)
        embed_and_store(augmented)
    """

    # Reasonable bounds for summary length
    MIN_SUMMARY_LENGTH = 50
    MAX_SUMMARY_LENGTH = 300
    DEFAULT_SUMMARY_LENGTH = 150

    # Prefix used in the augmented chunks (aids retrieval debugging)
    CONTEXT_PREFIX = "DOCUMENT CONTEXT"
    CHUNK_PREFIX = "CHUNK CONTENT"

    # Raw LLM responses are untrusted input: bound them before
    # sanitization so marker-filled responses cannot drive quadratic
    # scanning/allocation (PR #45 review, CWE-400).
    RAW_RESPONSE_CAP = 4096

    def __init__(
        self,
        llm_client: LLMClient,
        target_summary_length: int = DEFAULT_SUMMARY_LENGTH,
        preview_chars: int = 5000,
    ):
        """
        Initialise the SAC processor.

        Args:
            llm_client: Any object implementing a ``generate(prompt) → str``
                method (e.g., OpenAI, Anthropic, local model wrapper).
            target_summary_length: Desired character count for the fingerprint.
            preview_chars: Maximum characters of the source document sent to
                the LLM for summarisation (avoids token-limit issues on very
                large contracts).
        """
        self._llm = llm_client
        self._target_length = max(
            self.MIN_SUMMARY_LENGTH,
            min(target_summary_length, self.MAX_SUMMARY_LENGTH),
        )
        self._preview_chars = max(1, preview_chars)

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def generate_sac_chunks(
        self,
        document_text: str,
        chunks: List[str],
        document_id: Optional[str] = None,
    ) -> List[str]:
        """
        Augment every chunk with a global document fingerprint.

        Args:
            document_text: Full text of the source document.
            chunks: Pre-split text chunks.
            document_id: Optional human-readable document identifier.
                If not provided, a hash-based ID is generated.

        Returns:
            List of augmented chunk strings, same order as *chunks*.
        """
        if not chunks:
            return []

        doc_id = document_id or self._hash_id(document_text)
        # The deterministic hash is ALWAYS carried alongside, even when a
        # caller-supplied document_id exists — the hash is computable and
        # verifiable; the LLM summary is not (issue #42).
        deterministic_hash = self._hash_id(document_text)
        summary = self._generate_fingerprint(document_text)

        augmented: List[str] = []
        for i, chunk in enumerate(chunks):
            augmented_chunk = (
                f"{self.CONTEXT_PREFIX} [{doc_id}] "
                f"(deterministic hash: {deterministic_hash}) "
                f"[AI-GENERATED SUMMARY — UNTRUSTED CONTENT]: {summary}\n\n"
                f"{self.CHUNK_PREFIX} [{i + 1}/{len(chunks)}]: {chunk}"
            )
            augmented.append(augmented_chunk)

        return augmented

    def generate_fingerprint_only(self, document_text: str) -> str:
        """
        Return just the document fingerprint without augmenting chunks.

        Useful for inspection or caching.
        """
        return self._generate_fingerprint(document_text)

    # ------------------------------------------------------------------ #
    #  Internals                                                           #
    # ------------------------------------------------------------------ #

    def _generate_fingerprint(self, document_text: str) -> str:
        """
        Generate a concise, generic document fingerprint via the LLM.

        Generic summaries outperform expert-guided ones for retrieval.
        """
        preview = document_text[: self._preview_chars]

        prompt = (
            f"Summarize the following legal document text. Focus on extracting "
            f"the most important entities (parties, jurisdictions), core purpose, "
            f"and key legal topics. The summary must be concise — maximum "
            f"{self._target_length} characters — and optimized for providing "
            f"context to smaller text chunks.\n\n"
            f"Document:\n{preview}"
        )

        summary = self._llm.generate(prompt)

        # Defensive: handle None or empty LLM returns
        if not summary or not summary.strip():
            return self._hash_id(document_text)

        sanitized = self._sanitize_fingerprint(
            summary[: self.RAW_RESPONSE_CAP], self._target_length
        )
        if not sanitized:
            # Sanitization can strip everything (e.g., a response
            # consisting only of forged markers) — fall back to the
            # deterministic hash rather than embedding an empty
            # fingerprint (PR #45 review, Sentry).
            return self._hash_id(document_text)
        return sanitized

    @staticmethod
    def _sanitize_fingerprint(summary: str, target_length: int) -> str:
        """Treat LLM output as untrusted content (issue #42).

        Strips newlines/control characters and removes the processor's
        own structural markers, so a malicious or malfunctioning
        summary cannot forge chunk boundaries or inject context lines
        into every embedded chunk.
        """
        # Flatten to a single line: control characters become spaces
        summary = "".join(
            ch if ch.isprintable() and not ch.isspace() else " "
            for ch in summary
        )
        # Collapse whitespace runs left by the flattening
        summary = " ".join(summary.split())
        # Remove forged structural markers (case-insensitive) in a
        # bounded number of passes — repeated passes handle markers
        # reassembled by removal, and the bound keeps the work linear
        # (PR #45 review, CWE-400).
        marker_pattern = re.compile(
            rf"{re.escape(SACProcessor.CONTEXT_PREFIX)}|"
            rf"{re.escape(SACProcessor.CHUNK_PREFIX)}",
            re.IGNORECASE,
        )
        for _ in range(3):
            if not marker_pattern.search(summary):
                break
            summary = marker_pattern.sub("", summary)
            summary = " ".join(summary.split())
        # Enforce length limit
        if len(summary) > target_length:
            summary = summary[:target_length].rsplit(" ", 1)[0] + "…"
        return summary.strip()

    @staticmethod
    def _hash_id(text: str) -> str:
        """Deterministic short hash for document identification."""
        return "doc-" + hashlib.sha256(text.encode()).hexdigest()[:12]
