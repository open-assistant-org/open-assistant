"""Embedding service using ONNX Runtime for lightweight local text embeddings.

Uses the all-MiniLM-L6-v2 ONNX model (~80MB) with onnxruntime + tokenizers.
No PyTorch dependency — total footprint ~60MB vs ~2GB with torch.
"""

import hashlib
import struct

import numpy as np

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Default model from Hugging Face Hub
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Max token length for the model
_MAX_LENGTH = 256


class EmbeddingService:
    """Generates text embeddings using a local ONNX model."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model_name = model
        self._session = None
        self._tokenizer = None
        self._available: bool | None = None

    def _load_model(self) -> bool:
        """Lazy-load the ONNX model and tokenizer."""
        if self._session is not None:
            return True

        try:
            import onnxruntime as ort
            from huggingface_hub import hf_hub_download
            from tokenizers import Tokenizer

            # Download model files from HF Hub (cached after first download)
            model_path = hf_hub_download(self.model_name, "onnx/model.onnx")
            tokenizer_path = hf_hub_download(self.model_name, "tokenizer.json")

            # Load ONNX session
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 2
            self._session = ort.InferenceSession(
                model_path, opts, providers=["CPUExecutionProvider"]
            )

            # Load tokenizer
            self._tokenizer = Tokenizer.from_file(tokenizer_path)
            self._tokenizer.enable_truncation(max_length=_MAX_LENGTH)
            self._tokenizer.enable_padding(length=_MAX_LENGTH)

            logger.info(f"Loaded ONNX embedding model: {self.model_name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to load embedding model: {e}")
            return False

    def is_available(self) -> bool:
        """Check if embedding service is available."""
        if self._available is not None:
            return self._available

        self._available = self._load_model()
        return self._available

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        """Generate embeddings for a list of texts."""
        if not texts:
            return []

        if not self._load_model():
            return None

        try:
            # Truncate long texts before tokenization
            truncated = [t[:8000] if len(t) > 8000 else t for t in texts]

            # Tokenize
            encodings = self._tokenizer.encode_batch(truncated)

            input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
            token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

            # Run ONNX inference
            outputs = self._session.run(
                None,
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": token_type_ids,
                },
            )

            # Mean pooling over token embeddings, masked by attention
            token_embeddings = outputs[0]  # (batch, seq_len, hidden_dim)
            mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
            sum_embeddings = (token_embeddings * mask_expanded).sum(axis=1)
            sum_mask = mask_expanded.sum(axis=1).clip(min=1e-9)
            sentence_embeddings = sum_embeddings / sum_mask

            # L2 normalize
            norms = np.linalg.norm(sentence_embeddings, axis=1, keepdims=True).clip(min=1e-9)
            sentence_embeddings = sentence_embeddings / norms

            return [e.tolist() for e in sentence_embeddings]
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None

    def embed_single(self, text: str) -> list[float] | None:
        """Generate embedding for a single text."""
        result = self.embed([text])
        if result and len(result) > 0:
            return result[0]
        return None

    @staticmethod
    def serialize_embedding(embedding: list[float]) -> bytes:
        """Serialize an embedding vector to bytes for SQLite BLOB storage."""
        return struct.pack(f"{len(embedding)}f", *embedding)

    @staticmethod
    def deserialize_embedding(data: bytes) -> list[float]:
        """Deserialize an embedding vector from bytes."""
        n = len(data) // 4  # 4 bytes per float
        return list(struct.unpack(f"{n}f", data))

    @staticmethod
    def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)

    @staticmethod
    def content_hash(content: str) -> str:
        """Generate a SHA-256 hash of content for change detection."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
