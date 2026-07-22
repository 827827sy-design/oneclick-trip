from pathlib import Path

import numpy as np
import pytest

from app.vectorstore import BgeSmallZhV15EmbeddingFunction


MODEL_DIRECTORY = (
    Path(__file__).resolve().parents[1] / ".data/models/bge-small-zh-v1.5"
)


@pytest.mark.skipif(
    not (MODEL_DIRECTORY / "onnx/model_quantized.onnx").is_file(),
    reason="local BGE model is not downloaded",
)
def test_bge_embedding_is_normalized_and_semantically_relevant() -> None:
    embedding = BgeSmallZhV15EmbeddingFunction(MODEL_DIRECTORY)

    query = embedding.embed_query("成都大熊猫基地什么时候去最好")
    panda, hotpot = embedding(
        [
            "大熊猫基地建议早上前往，熊猫更活跃。",
            "成都火锅以牛油锅底和丰富菜品闻名。",
        ]
    )

    assert embedding.name() == "bge_small_zh_v1_5_onnx_int8"
    assert len(query) == 512
    assert np.linalg.norm(query) == pytest.approx(1, abs=1e-5)
    assert np.dot(query, panda) > np.dot(query, hotpot)
