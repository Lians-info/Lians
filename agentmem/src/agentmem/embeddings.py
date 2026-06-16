from __future__ import annotations
import hashlib
import numpy as np
from abc import ABC, abstractmethod
from typing import List
from .config import get_settings


class EmbeddingProvider(ABC):
    dim: int

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]:
        ...

    async def embed_one(self, text: str) -> List[float]:
        results = await self.embed([text])
        return results[0]


class VoyageProvider(EmbeddingProvider):
    """Voyage finance/domain embedding model."""
    dim = 1024

    def __init__(self):
        import voyageai
        settings = get_settings()
        self._client = voyageai.AsyncClient(api_key=settings.voyage_api_key)
        # voyage-finance-2 or voyage-3-large; confirm current model name before prod
        self._model = "voyage-3-large"

    async def embed(self, texts: List[str]) -> List[List[float]]:
        result = await self._client.embed(texts, model=self._model, input_type="document")
        return result.embeddings


class OpenAIProvider(EmbeddingProvider):
    """Cheap fallback for dev / CI."""
    dim = 1536  # text-embedding-3-small native dim, we'll truncate to 1024

    def __init__(self):
        from openai import AsyncOpenAI
        settings = get_settings()
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        resp = await self._client.embeddings.create(
            input=texts,
            model="text-embedding-3-small",
            dimensions=1024,  # request truncated output directly
        )
        return [item.embedding for item in resp.data]


class LocalProvider(EmbeddingProvider):
    """Deterministic bag-of-words for tests — zero API calls."""
    dim = 1024

    async def embed(self, texts: List[str]) -> List[List[float]]:
        results = []
        for text in texts:
            seed = int(hashlib.md5(text.encode()).hexdigest(), 16) % (2**31)
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(self.dim).astype(np.float32)
            vec = vec / (np.linalg.norm(vec) + 1e-9)
            results.append(vec.tolist())
        return results


def get_provider() -> EmbeddingProvider:
    settings = get_settings()
    match settings.embedding_provider:
        case "voyage":
            return VoyageProvider()
        case "openai":
            return OpenAIProvider()
        case _:
            return LocalProvider()


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        _provider = get_provider()
    return _provider
