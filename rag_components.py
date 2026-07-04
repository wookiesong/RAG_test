"""
Advanced RAG 핵심 컴포넌트

쿼리 확장, 임베딩, 검색, Rerank 등 RAG 파이프라인의
핵심 함수들을 포함합니다.
"""

import json
import time
from config import (
    get_openai,
    get_supabase,
    get_cohere,
    EMBEDDING_MODEL,
    QUERY_MODEL,
    RERANK_MODEL,
    RERANK_TOP_N,
    MULTI_QUERY_COUNT,
    RETRIEVE_K,
    TABLE_SEMANTIC,
    TABLE_CASCADE,
    TABLE_SEMANTIC_ENERGY,
    TABLE_CASCADE_ENERGY,
)


def expand_query(question: str, n: int = MULTI_QUERY_COUNT) -> list[str]:
    """
    질문을 n개의 다양한 표현으로 확장합니다.

    Args:
        question: 원래 질문
        n: 생성할 확장 질문 수 (기본값: 5)

    Returns:
        n개의 확장 질문 리스트 (원본 포함하지 않음)
    """
    client = get_openai()

    system_prompt = f"""사용자 질문을 {n}개의 다양한 표현으로 재구성하라.

지침:
- 원래 질문의 의미를 유지할 것
- 동의어/유사어 교체, 구체화/일반화, 질문 형태 변형 등 다양한 전략 사용
- 각 질문은 한 줄로 작성
- 한국어 도메인(법률/행정 공고)에 적합한 표현 사용
- JSON 배열 형식으로만 반환: ["질문1", "질문2", ...]"""

    try:
        # 먼저 JSON 모드로 시도
        try:
            response = client.chat.completions.create(
                model=QUERY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            result = json.loads(response.choices[0].message.content)
        except Exception:
            # DeepSeek 등 일부 모델은 response_format을 지원하지 않음
            # 폴백: 일반 텍스트 모드로 시도
            response = client.chat.completions.create(
                model=QUERY_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                temperature=0.7
            )
            content = response.choices[0].message.content

            # JSON 배열 추출 시도
            import re
            match = re.search(r'\[.*?\]', content, re.DOTALL)
            if match:
                result = json.loads(match.group())
            else:
                # JSON 배열을 찾지 못하면 줄 단위 파싱
                lines = [l.strip().strip('"\'') for l in content.split('\n') if l.strip()]
                result = [l for l in lines if l and not l.startswith('#')]

        # 다양한 가능한 키 시도
        queries = result.get("queries", result.get("questions", result.get("expanded_queries", result if isinstance(result, list) else [])))

        # n개 보장
        if len(queries) > n:
            queries = queries[:n]
        elif len(queries) < n:
            # 부족하면 원본으로 채움
            queries.extend([question] * (n - len(queries)))

        return queries

    except Exception as e:
        print(f"쿼리 확장 실패: {e}")
        # 실패 시 원본 질문으로 n개 채움
        return [question] * n


def embed(text: str) -> list[float]:
    """
    텍스트를 임베딩 벡터로 변환합니다.

    Args:
        text: 임베딩할 텍스트

    Returns:
        1536차원 임베딩 벡터
    """
    client = get_openai()

    try:
        response = client.embeddings.create(
            input=text,
            model=EMBEDDING_MODEL
        )
        return response.data[0].embedding

    except Exception as e:
        print(f"임베딩 실패: {e}")
        raise


def retrieve(
    table: str,
    query_embedding: list[float],
    k: int = RETRIEVE_K
) -> list[dict]:
    """
    Supabase에서 벡터 검색을 수행합니다.

    Args:
        table: 검색할 테이블 ("documents" 또는 "documents_cascade")
        query_embedding: 쿼리 임베딩 벡터
        k: 반환할 결과 수 (기본값: 10)

    Returns:
        검색 결과 리스트: [{id, content, metadata, similarity}, ...]
    """
    supabase = get_supabase()

    try:
        # RPC 함수 호출 (filter 파라미터 추가)
        function_name = f"match_{table}"
        result = supabase.rpc(
            function_name,
            {
                "query_embedding": query_embedding,
                "match_count": k,
                "filter": {}  # 빈 필터 (필요시 확장 가능)
            }
        ).execute()

        return result.data

    except Exception as e:
        print(f"검색 실패 (테이블: {table}): {e}")
        # RPC 실패 시 대안: 전체 가져와서 Python에서 필터링
        print("대안: 전체 문서를 가져와서 유사도 계산...")
        try:
            result = supabase.table(table).select("*").execute()
            all_docs = result.data

            # 코사인 유사도 계산 (NumPy 사용)
            import numpy as np
            query_vec = np.array(query_embedding)

            scored_docs = []
            for doc in all_docs:
                doc_vec = np.array(doc["embedding"])
                # 코사인 유사도
                similarity = np.dot(query_vec, doc_vec) / (np.linalg.norm(query_vec) * np.linalg.norm(doc_vec))
                scored_docs.append({
                    **doc,
                    "similarity": float(similarity)
                })

            # 상위 k개 정렬
            scored_docs.sort(key=lambda x: x["similarity"], reverse=True)
            return scored_docs[:k]

        except Exception as e2:
            print(f"대안 검색도 실패: {e2}")
            return []


def cohere_rerank(
    query: str,
    docs: list[dict],
    top_n: int = RERANK_TOP_N
) -> list[dict]:
    """
    Cohere Rerank로 문서를 재정렬합니다.

    Args:
        query: 원래 질문
        docs: 검색된 문서 리스트 [{id, content, metadata, similarity}, ...]
        top_n: 반환할 상위 문서 수 (기본값: 3)

    Returns:
        재정렬된 상위 top_n개 문서 (relevance_score 추가)
    """
    client = get_cohere()

    # content만 추출
    documents = [doc["content"] for doc in docs]

    try:
        response = client.rerank(
            model=RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=top_n
        )

        # 결과 재구성
        reranked_docs = []
        for result in response.results:
            original_doc = docs[result.index]
            reranked_docs.append({
                **original_doc,
                "relevance_score": result.relevance_score
            })

        return reranked_docs

    except Exception as e:
        print(f"Rerank 실패: {e}")
        # 실패 시 원본 순서대로 상위 top_n 반환
        return docs[:top_n]


def naive_rag(question: str, table: str) -> dict:
    """
    Naive RAG: 단일 쿼리 → 검색 → 상위 결과

    Args:
        question: 사용자 질문
        table: 검색할 테이블 ("documents" 또는 "documents_cascade")

    Returns:
        {results: [...], execution_time: float, method: "naive"}
    """
    start_time = time.time()

    # 1. 임베딩
    query_embedding = embed(question)

    # 2. 검색
    retrieved_docs = retrieve(table, query_embedding, k=RETRIEVE_K)

    # 3. 상위 3개 선택 (Rerank 없음)
    top_results = retrieved_docs[:RERANK_TOP_N]

    execution_time = time.time() - start_time

    return {
        "results": top_results,
        "execution_time": execution_time,
        "method": "naive",
        "table": table,
        "retrieved_count": len(retrieved_docs)
    }


def advanced_rag(question: str, table: str) -> dict:
    """
    Advanced RAG: Multi-Query → 검색 → 합집합 → Rerank

    Args:
        question: 사용자 질문
        table: 검색할 테이블 ("documents" 또는 "documents_cascade")

    Returns:
        {results: [...], execution_time: float, method: "advanced", expanded_queries: [...]}
    """
    start_time = time.time()

    # 1. 쿼리 확장
    expanded_queries = expand_query(question, n=MULTI_QUERY_COUNT)
    query_expansion_time = time.time() - start_time

    # 2. 각 확장 쿼리별 검색 및 합집합
    all_retrieved = {}
    for i, expanded_query in enumerate(expanded_queries):
        query_embedding = embed(expanded_query)
        retrieved_docs = retrieve(table, query_embedding, k=RETRIEVE_K)

        # id 기준 dedup
        for doc in retrieved_docs:
            doc_id = doc["id"]
            if doc_id not in all_retrieved:
                all_retrieved[doc_id] = doc
            # 이미 있는 경우 더 높은 similarity 유지

    retrieved_list = list(all_retrieved.values())
    retrieval_time = time.time() - start_time - query_expansion_time

    # 3. Rerank
    reranked_docs = cohere_rerank(question, retrieved_list, top_n=RERANK_TOP_N)
    rerank_time = time.time() - start_time - query_expansion_time - retrieval_time

    execution_time = time.time() - start_time

    return {
        "results": reranked_docs,
        "execution_time": execution_time,
        "method": "advanced",
        "table": table,
        "expanded_queries": expanded_queries,
        "retrieved_count": len(retrieved_list),
        "timing": {
            "query_expansion": query_expansion_time,
            "retrieval": retrieval_time,
            "rerank": rerank_time
        }
    }


def run_all_combos(question: str, table_semantic: str = TABLE_SEMANTIC, table_cascade: str = TABLE_CASCADE) -> dict:
    """
    4가지 조합으로 RAG를 실행하고 비교합니다.

    조합:
    1. Naive + Semantic (table_semantic)
    2. Naive + Cascade (table_cascade)
    3. Advanced + Semantic (table_semantic)
    4. Advanced + Cascade (table_cascade)

    Args:
        question: 사용자 질문
        table_semantic: 시맨틱 청킹 테이블 (기본값: TABLE_SEMANTIC)
        table_cascade: 계층형 청킹 테이블 (기본값: TABLE_CASCADE)

    Returns:
        {naive_semantic: {...}, naive_cascade: {...}, advanced_semantic: {...}, advanced_cascade: {...}}
    """
    results = {}

    print(f"\n질문: {question}")
    print("=" * 80)

    # Naive + Semantic
    print(f"1. Naive + Semantic ({table_semantic}) 실행 중...")
    results["naive_semantic"] = naive_rag(question, table_semantic)
    print(f"   완료 ({results['naive_semantic']['execution_time']:.2f}초)")

    # Naive + Cascade
    print(f"2. Naive + Cascade ({table_cascade}) 실행 중...")
    results["naive_cascade"] = naive_rag(question, table_cascade)
    print(f"   완료 ({results['naive_cascade']['execution_time']:.2f}초)")

    # Advanced + Semantic
    print(f"3. Advanced + Semantic ({table_semantic}) 실행 중...")
    results["advanced_semantic"] = advanced_rag(question, table_semantic)
    print(f"   완료 ({results['advanced_semantic']['execution_time']:.2f}초)")

    # Advanced + Cascade
    print(f"4. Advanced + Cascade ({table_cascade}) 실행 중...")
    results["advanced_cascade"] = advanced_rag(question, table_cascade)
    print(f"   완료 ({results['advanced_cascade']['execution_time']:.2f}초)")

    return results


def format_comparison_output(question: str, results: dict) -> str:
    """
    4가지 조합 결과를 2×2 표 형식으로 포맷팅합니다.

    Args:
        question: 사용자 질문
        results: run_all_combos의 결과

    Returns:
        포맷팅된 문자열
    """
    output = []
    output.append(f"\n질문: {question}")
    output.append("=" * 80)

    # 헤더
    output.append(f"{'':<15} | {'시맨틱 (documents)':<40} | {'계층형 (documents_cascade)':<40}")
    output.append("-" * 100)

    # Naive 행
    naive_sem = results["naive_semantic"]["results"]
    naive_cas = results["naive_cascade"]["results"]

    output.append(f"{'Naive':<15} |")
    for i in range(RERANK_TOP_N):
        if i < len(naive_sem):
            doc = naive_sem[i]
            score = doc.get("relevance_score", doc.get("similarity", 0))
            preview = doc["content"][:60].replace("\n", " ")
            output.append(f"  [{doc['id']}] {score:.2f} {preview}")
        else:
            output.append(f"  (결과 없음)")

    output.append(f"{'':<15} |")

    for i in range(RERANK_TOP_N):
        if i < len(naive_cas):
            doc = naive_cas[i]
            score = doc.get("relevance_score", doc.get("similarity", 0))
            preview = doc["content"][:60].replace("\n", " ")
            output.append(f"  [{doc['id']}] {score:.2f} {preview}")
        else:
            output.append(f"  (결과 없음)")

    # Advanced 행
    output.append("-" * 100)
    adv_sem = results["advanced_semantic"]["results"]
    adv_cas = results["advanced_cascade"]["results"]

    output.append(f"{'Advanced':<15} |")
    for i in range(RERANK_TOP_N):
        if i < len(adv_sem):
            doc = adv_sem[i]
            score = doc.get("relevance_score", doc.get("similarity", 0))
            preview = doc["content"][:60].replace("\n", " ")
            output.append(f"  [{doc['id']}] {score:.2f} {preview}")
        else:
            output.append(f"  (결과 없음)")

    output.append(f"{'':<15} |")

    for i in range(RERANK_TOP_N):
        if i < len(adv_cas):
            doc = adv_cas[i]
            score = doc.get("relevance_score", doc.get("similarity", 0))
            preview = doc["content"][:60].replace("\n", " ")
            output.append(f"  [{doc['id']}] {score:.2f} {preview}")
        else:
            output.append(f"  (결과 없음)")

    # 실행시간 정보
    output.append("-" * 100)
    output.append("실행시간 (초):")
    output.append(f"{'':<15} | Semantic: {results['naive_semantic']['execution_time']:.2f} | Cascade: {results['naive_cascade']['execution_time']:.2f}")
    output.append(f"{'':<15} | Semantic: {results['advanced_semantic']['execution_time']:.2f} | Cascade: {results['advanced_cascade']['execution_time']:.2f}")

    # Advanced의 확장 쿼리 표시
    expanded = results["advanced_semantic"].get("expanded_queries", [])
    if expanded:
        output.append("-" * 100)
        output.append("확장된 쿼리:")
        for i, q in enumerate(expanded, 1):
            output.append(f"  {i}. {q}")

    return "\n".join(output)
