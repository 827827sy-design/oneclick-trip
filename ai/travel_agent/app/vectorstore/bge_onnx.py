from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from huggingface_hub import snapshot_download
from tokenizers import Tokenizer


class BgeSmallZhV15EmbeddingFunction(EmbeddingFunction[Documents]):
    """CPU-friendly BGE-small-zh-v1.5 embeddings backed by ONNX Runtime."""

    dimension = 512
    model_id = "Xenova/bge-small-zh-v1.5"
    model_file = "onnx/model_quantized.onnx"
    query_instruction = "为这个句子生成表示以用于检索相关文章："

    def __init__(
        self,
        model_directory: Path | str,
        *,
        auto_download: bool = False,
        max_length: int = 512,
        batch_size: int = 16,
    ) -> None:
        self.model_directory = Path(model_directory).resolve()
        self.max_length = max_length
        self.batch_size = batch_size
        if auto_download:
            self.ensure_model()
        self._require_model_files()

        self._tokenizer = Tokenizer.from_file(
            str(self.model_directory / "tokenizer.json")
        )
        self._tokenizer.enable_truncation(max_length=max_length)
        self._tokenizer.enable_padding(
            pad_id=self._tokenizer.token_to_id("[PAD]") or 0,
            pad_token="[PAD]",
        )
        self._session = ort.InferenceSession(
            str(self.model_directory / self.model_file),
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {item.name for item in self._session.get_inputs()}

    def __call__(self, input: Documents) -> Embeddings:
        return self._embed(list(input))

    def embed_query(self, query: str) -> list[float]:
        return self._embed([f"{self.query_instruction}{query}"])[0]

    @staticmethod
    def name() -> str:
        return "bge_small_zh_v1_5_onnx_int8"

    def get_config(self) -> dict[str, Any]:
        return {
            "model_directory": str(self.model_directory),
            "max_length": self.max_length,
            "batch_size": self.batch_size,
        }

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> BgeSmallZhV15EmbeddingFunction:
        return BgeSmallZhV15EmbeddingFunction(
            config["model_directory"],
            max_length=int(config.get("max_length", 512)),
            batch_size=int(config.get("batch_size", 16)),
        )

    def ensure_model(self) -> None:
        if self._model_files_exist():
            return
        self.model_directory.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=self.model_id,
            local_dir=self.model_directory,
            allow_patterns=[
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
                "vocab.txt",
                "config.json",
                self.model_file,
            ],
        )

    def _embed(self, texts: list[str]) -> Embeddings:
        if not texts:
            return []
        embeddings: list[list[float]] = []
        for offset in range(0, len(texts), self.batch_size):
            batch = texts[offset : offset + self.batch_size]
            encodings = self._tokenizer.encode_batch(batch)
            feeds = {
                "input_ids": np.asarray(
                    [encoding.ids for encoding in encodings], dtype=np.int64
                ),
                "attention_mask": np.asarray(
                    [encoding.attention_mask for encoding in encodings], dtype=np.int64
                ),
            }
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = np.asarray(
                    [encoding.type_ids for encoding in encodings], dtype=np.int64
                )
            feeds = {name: value for name, value in feeds.items() if name in self._input_names}
            last_hidden_state = self._session.run(None, feeds)[0]
            pooled = last_hidden_state[:, 0, :]
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            normalized = pooled / np.clip(norms, 1e-12, None)
            embeddings.extend(normalized.astype(np.float32).tolist())
        return embeddings

    def _require_model_files(self) -> None:
        if self._model_files_exist():
            return
        raise FileNotFoundError(
            "BGE model files are missing. Enable BGE_AUTO_DOWNLOAD or run the "
            "documented model download command before starting FastAPI."
        )

    def _model_files_exist(self) -> bool:
        return (
            (self.model_directory / "tokenizer.json").is_file()
            and (self.model_directory / self.model_file).is_file()
        )
