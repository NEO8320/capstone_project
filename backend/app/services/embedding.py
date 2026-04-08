"""
Ko-SBERT 임베딩 서비스 모듈
============================

sentence-transformers 라이브러리의 Ko-SBERT 모델을 사용하여
텍스트를 768차원 벡터로 인코딩한다.

사용 모델: snunlp/KR-SBERT-V40K-klueNLI-augSTS
  - 한국어에 특화된 Sentence-BERT
  - 출력 차원: 768

주요 함수:
  - get_embedding(text)       : 단일 텍스트 → 768차원 벡터
  - get_embeddings(texts)     : 배치 텍스트 → 768차원 벡터 리스트
  - get_category_embedding(cat): 카테고리명 → 대표 벡터 (콜드 스타트용)
"""

import asyncio
from functools import lru_cache

import numpy as np

from app.core.config import settings

# ── 모델 싱글턴 (lazy loading) ──
# sentence-transformers는 무거우므로 최초 호출 시 한 번만 로드한다.
_model = None


def _load_model():
    """
    Ko-SBERT 모델을 로드한다 (싱글턴).
    최초 호출 시 모델 파일을 다운로드/캐싱하므로 수 초 소요될 수 있다.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        print(f"[Embedding] Ko-SBERT 모델 로딩: {settings.EMBEDDING_MODEL_NAME}")
        _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
        print(f"[Embedding] 모델 로딩 완료 (차원: {_model.get_sentence_embedding_dimension()})")
    return _model


def get_embedding_sync(text: str) -> list[float]:
    """
    텍스트를 768차원 벡터로 인코딩한다 (동기 버전).

    Args:
        text: 인코딩할 텍스트 (기사 제목 + 요약 권장)

    Returns:
        768차원 float 리스트 (pgvector에 저장 가능한 형식)
    """
    model = _load_model()
    # normalize_embeddings=True: 코사인 유사도 연산을 단순 내적으로 대체 가능
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def get_embeddings_batch_sync(texts: list[str]) -> list[list[float]]:
    """
    여러 텍스트를 배치로 인코딩한다 (동기 버전).
    GPU가 있으면 배치 처리가 개별 처리보다 훨씬 빠르다.

    Args:
        texts: 인코딩할 텍스트 리스트

    Returns:
        768차원 벡터 리스트의 리스트
    """
    model = _load_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32)
    return embeddings.tolist()


async def get_embedding(text: str) -> list[float]:
    """
    텍스트를 768차원 벡터로 인코딩한다 (비동기 래퍼).
    CPU 집약적 작업이므로 별도 스레드에서 실행하여 이벤트 루프를 블로킹하지 않는다.

    Args:
        text: 인코딩할 텍스트 (기사 '제목 + 요약'을 합쳐서 전달)

    Returns:
        768차원 float 리스트
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_embedding_sync, text)


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    여러 텍스트를 배치로 인코딩한다 (비동기 래퍼).

    Args:
        texts: 인코딩할 텍스트 리스트

    Returns:
        768차원 벡터 리스트의 리스트
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_embeddings_batch_sync, texts)


@lru_cache(maxsize=10)
def _get_category_embedding_cached(category: str) -> tuple:
    """
    카테고리 대표 벡터를 생성한다 (캐싱됨).
    lru_cache는 list를 키로 사용할 수 없으므로 tuple로 변환하여 캐싱.
    """
    return tuple(get_embedding_sync(category))


async def get_category_embedding(category: str) -> list[float]:
    """
    카테고리명을 768차원 대표 벡터로 변환한다.
    신규 사용자의 콜드 스타트 시 관심 카테고리 2개의 평균 벡터를 구하는 데 사용.

    Args:
        category: 카테고리명 (예: "정치", "경제")

    Returns:
        768차원 float 리스트
    """
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _get_category_embedding_cached, category)
    return list(result)


async def compute_cold_start_vector(categories: list[str]) -> list[float]:
    """
    신규 사용자의 콜드 스타트 관심 벡터를 생성한다.
    선택한 2개 카테고리의 대표 벡터를 평균하여 초기 관심 벡터로 설정.

    공식: V_interest = (V_cat1 + V_cat2) / 2

    Args:
        categories: 사용자가 선택한 관심 카테고리 2개

    Returns:
        768차원 float 리스트 (정규화된 평균 벡터)
    """
    vectors = []
    for cat in categories:
        vec = await get_category_embedding(cat)
        vectors.append(np.array(vec))

    # 평균 벡터 계산
    avg_vector = np.mean(vectors, axis=0)

    # L2 정규화 (코사인 유사도 연산 최적화)
    norm = np.linalg.norm(avg_vector)
    if norm > 0:
        avg_vector = avg_vector / norm

    return avg_vector.tolist()


def get_zero_vector() -> list[float]:
    """
    768차원 영벡터를 반환한다.
    신규 사용자의 비관심 벡터(disinterest_vector) 초기값으로 사용.
    """
    return [0.0] * settings.EMBEDDING_DIM
