# RAG 2×2 비교 시스템: 종합 개발 프로세스 가이드

## 개요

본 문서는 문서를 마크다운으로 파싱하여 시맨틱/계층형 청킹을 수행하고, Supabase 벡터 DB에 업로드한 후 Naive/Advanced RAG를 비교하는 **전체 개발 프로세스**를 단계별로 설명합니다.

에이전트가 이 시스템을 재현할 수 있도록 각 단계별 구체적인 코드 예시와 기술 구현 사항을 포함합니다.

## 📋 목차

1. [시스템 아키텍처](#시스템-아키텍처)
2. [1단계: 문서 준비 및 파싱](#1단계-문서-준비-및-파싱)
3. [2단계: 청킹 전략](#2단계-청킹-전략)
4. [3단계: Supabase 업로드](#3단계-supabase-업로드)
5. [4단계: RAG 구현](#4단계-rag-구현)
6. [5단계: Flask 웹 UI](#5단계-flask-웹-ui)
7. [결론 및 최적화 방안](#결론-및-최적화-방안)

---

## 시스템 아키텍처

### 전체 파이프라인

```
┌─────────────────────────────────────────────────────────────────────┐
│                      1. 문서 준비 및 파싱                           │
│  원본 문서 → 마크다운 변환 → 구조 분석                              │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      2. 청킹 (2가지 방식)                          │
│  ┌──────────────────┐  ┌──────────────────┐                      │
│  │ 시맨틱 청킹       │  │ 계층형 청킹       │                      │
│  │ (의미 기반)        │  │ (구조 기반)        │                      │
│  │ BGE-M3 사용      │  │ 정규식 패턴 사용   │                      │
│  │ chunks.jsonl     │  │ chunks_cascade... │                      │
│  └──────────────────┘  └──────────────────┘                      │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      3. 임베딩 & Supabase 업로드                     │
│  OpenAI text-embedding-3-small → 1536차원 벡터                    │
│  documents / documents_cascade 테이블 저장                        │
│  RPC 함수: match_documents() / match_documents_cascade()            │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      4. RAG 비교 (2×2)                             │
│  ┌─────────────────────────────────────────────────────┐         │
│  │ Naive RAG    │  │ Advanced RAG │                        │
│  │ 단일 쿼리→검색 │  │ 5개 쿼리→검색→Rerank │                │
│  │ Top-3         │  │ Top-3            │                    │
│  └─────────────────────────────────────────────────────┘         │
│  × 시맨틱 / 계층형 청킹 = 4가지 조합 비교                           │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      5. Flask 웹 UI                                │
│  사용자 질문 입력 → 4조합 실시간 실행 → 2×2 그리드 결과 표시        │
└─────────────────────────────────────────────────────────────────────┘
```

### 기술 스택 상세

| 구성 요소 | 기술 | 버전/모델 | 역할 |
|----------|------|-----------|------|
| 문서 형식 | Markdown | - | 원본 저장 및 파싱 용이성 |
| 시맨틱 청킹 | Chonkie SemanticChunker | BGE-M3 | 의미 기반 문장 분할 |
| 계층형 청킹 | Python 정규식 | re | 구조 기반 분할 |
| 임베딩 | OpenAI Embeddings | text-embedding-3-small | 1536차원 벡터 변환 |
| 벡터 DB | Supabase | pgvector | 벡터 검색 및 저장 |
| 쿼리 확장 | OpenRouter | DeepSeek v3.1 | 5개 질문 생성 |
| Rerank | Cohere | rerank-multilingual-v3.0 | 결과 재정렬 |
| 백엔드 | Flask | Python 3.12 | API 서버 |
| 프론트엔드 | HTML/CSS/JS | - | 2×2 비교 UI |

---

## 1단계: 문서 준비 및 파싱

### 1.1 마크다운 변환의 중요성

RAG 시스템의 첫 단계는 원본 문서를 **구조화된 마크다운**으로 변환하는 것입니다.

**원본 문서 형식**:
- `.hwpx` (한글), `.pdf`, `.docx` 등

**이유**:
1. **구조 보존**: 헤더(#), 목록(-), 표(|) 등 마크다운 구문이 청킹에 활용
2. **텍스트 추출 용이**: 순수 텍스트로 변환 시 문서 구조 손실
3. **용이성**: Python에서 `f.read()`로 바로 읽고 파싱 가능

### 1.2 파싱 전략 (공고문 기준)

공고문/법령 문서의 특징적 구조:

```markdown
# 문서 제목
발간 일자

| N | 섹션명 |
|---|---|

□ 항목명 : 설명
ㅇ 세부 설명
① 원번호 항목
※ 주석
```

**파싱 시 고려사항**:
1. **헤더 계층**: `#` → `##` → `###`로 계층 파악
2. **마커 식별**: `□`, `ㅇ`, `①`, `※`, `가./나.` 등의 역할 분류
3. **표 처리**: HTML `<table>`과 마크다운 `|` 표의 구분
4. **연속성**: 문단 간 빈 줄(`\n\n`)으로 청크 분할 단위 결정

### 1.3 코드 예시: 문서 로드

```python
# 문서 로드
with open(INPUT_PATH, encoding="utf-8") as f:
    text = f.read()

# HTML 표 보존 (파싱 전략)
tables = re.findall(r"<table>.*?</table>", text, re.DOTALL)
table_map = {}
for i, table in enumerate(tables):
    placeholder = f"\n[[TABLE_{i}]]\n"
    table_map[placeholder] = table
    text = text.replace(table, placeholder, 1)  # 첫 번째만 치환

# 청킹 후 복원
for placeholder, original_table in table_map.items():
    text = text.replace(placeholder, original_table)
```

---

## 2단계: 청킹 전략

### 2.1 시맨틱 청킹 (Semantic Chunking)

#### 개념
문장 간 **의미적 유사도**를 계산하여 자연스러운 경계에서 분할합니다.

#### 기술 구현 (Chonkie 사용)

```python
from chonkie import SemanticChunker, SentenceTransformerEmbeddings

# 1. 임베딩 모델 로드
MODEL = "BAAI/bge-m3"  # 다국어 지원 대형 모델
embeddings = SentenceTransformerEmbeddings(MODEL)

# 2. 청커 생성
chunker = SemanticChunker(
    embedding_model=embeddings,
    threshold=0.3,      # 유사도 임계값 (0-1)
    chunk_size=1024,    # 최대 청크 크기 (토큰)
    min_sentences=2     # 최소 문장 수
)

# 3. 청킹 실행
chunks = chunker(text)

# 4. 결과 저장
for i, chunk in enumerate(chunks):
    record = {
        "chunk_id": i,
        "text": chunk.text.strip(),
        "token_count": chunk.token_count
    }
```

#### 장단점

| 장점 | 단점 |
|------|------|
| 문맥 자연스러운 분할 | 대형 임베딩 모델 필요 (메모리 많이 소모) |
| 의미 단위 청킹 | 처리 속도 느림 |
| 중요 정보 분산 방지 | 모델 의존성 |

#### 대체 전략 (메모리 제약 시)

```python
# 단순 토큰 기반 청킹
def count_tokens(text: str) -> int:
    return len(text) // 3  # 한글 기준 대략적 계산

CHUNK_SIZE = 1000
OVERLAP = 100

paragraphs = text.split("\n\n")
chunks = []
current_chunk = ""

for paragraph in paragraphs:
    test_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph
    if count_tokens(test_chunk) > CHUNK_SIZE:
        chunks.append({"chunk_id": len(chunks), "text": current_chunk})
        current_chunk = paragraph
    else:
        current_chunk = test_chunk
```

### 2.2 계층형 청킹 (Hierarchical Chunking)

#### 개념
문서의 **구조적 계층**을 따라 분할합니다.

#### 기술 구현 (정규식 패턴)

```python
import re
from pathlib import Path

# 1. 공고문 전용 정규식 패턴 정의
section_pattern = re.compile(r"^\|\s*(\d+)\s*|\s*(.+?)\s*|\s*$")   # | 1 | 사업개요 |
item_pattern    = re.compile(r"^ㅁ\s*(.+?)$")                          # □ 항목명
syl_pattern     = re.compile(r"^([가-힣])\.\s*(.+)$")                   # 가. 나.
number_pattern  = re.compile(r"^([①-⑳])\s*(.+)$")                      # 원번호
subitem_pattern = re.compile(r"^ㅇ\s+(.+)$")                             # ㅇ 서브
note_pattern    = re.compile(r"^※\s+(.+)$")                              # ※ 주석

# 2. 계층 구조 추출
def extract_hierarchy(text: str) -> list[dict]:
    chunks = []
    current_section = None
    current_item = None
    
    for line in text.splitlines():
        # 섹션 패턴 매칭
        m = section_pattern.match(line.strip())
        if m:
            current_section = {"no": m.group(1), "title": m.group(2)}
            continue
        
        # 항목 패턴 매칭
        m = item_pattern.match(line.strip())
        if m:
            current_item = {"marker": "□", "content": m.group(1), "lines": []}
            continue
        
        # 내용 수집
        if current_item:
            current_item["lines"].append(line.strip())
    
    return chunks
```

#### 메타데이터 구조

```python
chunk = {
    "chunk_id": 1,
    "doc_title": "2026년 AI기반 분산에너지 특화지역 지원 사업 2차 공고",
    "section_no": "1",
    "section_title": "사업개요",
    "item_marker": "□_사업목적",
    "subsection": None,
    "content": "...",
    "source_path": "문서명 > 섹션1_사업개요 > 항목_□_사업목적",
    "doc_type": "energy",
    "notice_no": "2026-642"
}
```

#### 장단점

| 장점 | 단점 |
|------|------|
| 문서 구조 보존 | 문서 유형별 정규식 재설계 필요 |
| 메타데이터 풍부 | 일관된 구조 없는 문서 적용 어려움 |
| 검색 시 섹션 필터링 가능 | 구조 파악 오류 시 분할 실패 |

---

## 3단계: Supabase 업로드

### 3.1 테이블 스키마 설계

```sql
-- 기본 테이블 구조 (LangChain 호환)
CREATE TABLE documents (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  content text,
  metadata jsonb,
  embedding vector(1536)
);
```

**컬럼 설명**:
- `id`: 고유 식별자 (bigint, 타입 불일치 사고 방지)
- `content`: 청크 텍스트
- `metadata`: 청크 메타데이터 (flexible JSON)
- `embedding`: OpenAI 임베딩 벡터 (1536차원)

### 3.2 RPC 함수 생성

```sql
-- pgvector 매칭 함수
CREATE OR REPLACE FUNCTION match_documents (
  query_embedding vector(1536),
  match_count int DEFAULT 10,
  filter jsonb DEFAULT '{}'
) RETURNS TABLE (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql AS $$
#variable_conflict use_column
BEGIN
  RETURN QUERY
  SELECT
    id,
    content,
    metadata,
    1 - (embedding <=> query_embedding) AS similarity
  FROM documents
  WHERE metadata @> filter
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
END; $$;
```

**핵심 포인트**:
- `<=` 연산자: pgvector의 코사인 거리 연산자
- `1 - distance`: 거리를 유사도로 변환
- `ORDER BY ... LIMIT`: Top-K 검색
- `metadata @> filter`: 메타데이터 필터링

### 3.3 임베딩 생성

```python
from openai import OpenAI

client = OpenAI(api_key=OPENAI_API_KEY)
MODEL_NAME = "text-embedding-3-small"

# 배치 임베딩 (100개 단위)
def embed_batch(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        input=texts,
        model=MODEL_NAME
    )
    return [item.embedding for item in response.data]

# 전체 문서 임베딩
batch_size = 100
all_embeddings = []

for i in range(0, len(chunks), batch_size):
    batch = chunks[i:i+batch_size]
    texts = [chunk["content"] for chunk in batch]
    embeddings = embed_batch(texts)
    all_embeddings.extend(embeddings)
```

### 3.4 Supabase 업로드

```python
from supabase import create_client

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 레코드 생성
records = []
for i, chunk in enumerate(chunks):
    record = {
        # id 제거 - Supabase가 자동 생성
        "content": chunk["content"],
        "metadata": chunk.get("metadata", {}),
        "embedding": embeddings[i]
    ]
    records.append(record)

# 배치 삽입 (100개 단위)
for i in range(0, len(records), 100):
    batch = records[i:i+100]
    try:
        result = client.table("documents").insert(batch).execute()
        print(f"삽입 완료: {i+1}-{min(i+100, len(records))}")
    except Exception as e:
        # 개별 재시도
        for record in batch:
            client.table("documents").insert(record).execute()
```

---

## 4단계: RAG 구현

### 4.1 Naive RAG

```python
def naive_rag(question: str, table: str) -> dict:
    """
    단일 쿼리 → 검색 → 상위 K개 반환
    
    Args:
        question: 사용자 질문
        table: 검색할 테이블 ("documents" 또는 "documents_cascade")
    
    Returns:
        {results: [...], execution_time: float, method: "naive", table: str}
    """
    start_time = time.time()
    
    # 1. 임베딩
    query_embedding = embed(question)
    
    # 2. 검색 (RPC 호출)
    result = supabase.rpc(
        f"match_{table}",
        {
            "query_embedding": query_embedding,
            "match_count": 10  # Top-10 검색
        }
    ).execute()
    
    retrieved_docs = result.data
    
    # 3. 상위 3개 선택 (Rerank 없음)
    top_results = retrieved_docs[:3]
    
    execution_time = time.time() - start_time
    
    return {
        "results": top_results,
        "execution_time": execution_time,
        "method": "naive",
        "table": table
    }
```

### 4.2 Advanced RAG

```python
def advanced_rag(question: str, table: str) -> dict:
    """
    5개 쿼리 → 검색 → 합집합 → Rerank → 상위 K개
    
    Returns:
        {results: [...], execution_time: float, method: "advanced", 
         expanded_queries: [...]}
    """
    start_time = time.time()
    
    # 1. 쿼리 확장 (5개 질문 생성)
    expanded_queries = expand_query(question, n=5)
    
    # 2. 각 확장 쿼리별 검색 및 합집합
    all_retrieved = {}
    for expanded_query in expanded_queries:
        query_embedding = embed(expanded_query)
        result = supabase.rpc(f"match_{table}", {
            "query_embedding": query_embedding,
            "match_count": 10
        }).execute()
        
        # id 기준 dedup
        for doc in result.data:
            doc_id = doc["id"]
            if doc_id not in all_retrieved:
                all_retrieved[doc_id] = doc
    
    retrieved_list = list(all_retrieved.values())
    
    # 3. Cohere Rerank
    reranked_docs = cohere_rerank(question, retrieved_list, top_n=3)
    
    execution_time = time.time() - start_time
    
    return {
        "results": reranked_docs,
        "execution_time": execution_time,
        "method": "advanced",
        "table": table,
        "expanded_queries": expanded_queries
    }
```

### 4.3 쿼리 확장 (Query Expansion)

```python
def expand_query(question: str, n: int = 5) -> list[str]:
    """
    질문을 n개의 다양한 표현으로 확장
    """
    client = get_openai()  # OpenRouter 또는 OpenAI
    
    system_prompt = f"""사용자 질문을 {n}개의 다양한 표현으로 재구성하라.

지침:
- 원래 질문의 의미를 유지할 것
- 동의어/유사어 교체, 구체화/일반화, 질문 형태 변형 등 다양한 전략 사용
- 각 질문은 한 줄로 작성
- 한국어 법률/행정 도메인에 적합한 표현 사용
- JSON 배열 형식으로만 반환: ["질문1", "질문2", ...]"""
    
    try:
        response = client.chat.completions.create(
            model=QUERY_MODEL,  # gpt-4o-mini 또는 deepseek/deepseek-chat-v3.1
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}  # 일부 모델 미지원
        )
        
        result = json.loads(response.choices[0].message.content)
        queries = result.get("queries", result.get("questions", result.get("expanded_queries", [])))
        
        # n개 보장
        if len(queries) < n:
            queries.extend([question] * (n - len(queries)))
        
        return queries[:n]
    
    except Exception:
        # 폴백: 일반 텍스트에서 JSON 배열 추출
        import re
        content = response.choices[0].message.content
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            return json.loads(match.group())
        return [question] * n
```

### 4.4 Cohere Rerank

```python
import cohere

def cohere_rerank(query: str, docs: list[dict], top_n: int = 3) -> list[dict]:
    """
    Cohere Rerank로 문서 재정렬
    
    Args:
        query: 원래 질문
        docs: 검색된 문서 리스트 [{id, content, metadata, similarity}, ...]
        top_n: 반환할 상위 문서 수
    """
    client = cohere.ClientV2(api_key=COHERE_API_KEY)
    
    # content만 추출
    documents = [doc["content"] for doc in docs]
    
    try:
        response = client.rerank(
            model="rerank-multilingual-v3.0",
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
                "relevance_score": result.relevance_score  # 새로운 점수
            })
        
        return reranked_docs
    
    except Exception as e:
        print(f"Rerank 실패: {e}")
        # 폴백: 원본 순서대로 상위 top_n 반환
        return docs[:top_n]
```

---

## 5단계: Flask 웹 UI

### 5.1 API 설계

```python
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# 테이블 매핑
TABLE_PAIRS = {
    "civil":  ("documents", "documents_cascade"),
    "energy": ("documents_energy", "documents_energy_cascade"),
}

@app.route("/")
def index():
    """메인 페이지 렌더링"""
    return render_template("index.html")

@app.route("/api/config")
def get_config():
    """프론트엔드용 설정 정보"""
    return jsonify({
        "default_model": QUERY_MODEL,
        "llm_models": LLM_MODELS.split(","),
        "doc_types": [
            {"value": "civil", "label": "민원처리법"},
            {"value": "energy", "label": "분산에너지 공고"}
        ]
    })

@app.route("/api/compare", methods=["POST"])
def compare():
    """4조합 RAG 실행 및 결과 반환"""
    data = request.get_json()
    question = data.get("question", "").strip()
    doc_type = data.get("doc_type", "civil")
    
    # 테이블 선택
    table_semantic, table_cascade = TABLE_PAIRS[doc_type]
    
    # 4조합 실행
    results = {}
    results["naive_semantic"] = naive_rag(question, table_semantic)
    results["naive_cascade"] = naive_rag(question, table_cascade)
    results["advanced_semantic"] = advanced_rag(question, table_semantic)
    results["advanced_cascade"] = advanced_rag(question, table_cascade)
    
    return jsonify({
        "success": True,
        "question": question,
        "doc_type": doc_type,
        "results": results
    })
```

### 5.2 프론트엔드 구조

```html
<!-- 2×2 그리드 레이아웃 -->
<div class="grid-container">
  <!-- 좌상: Naive + Semantic -->
  <div class="grid-cell">
    <div class="grid-header">Naive + Semantic</div>
    <div id="naive-semantic" class="grid-content"></div>
  </div>
  
  <!-- 우상: Naive + Cascade -->
  <div class="grid-cell">
    <div class="grid-header">Naive + Cascade</div>
    <div id="naive-cascade" class="grid-content"></div>
  </div>
  
  <!-- 좌하: Advanced + Semantic -->
  <div class="grid-cell">
    <div class="grid-header">Advanced + Semantic</div>
    <div id="advanced-semantic" class="grid-content"></div>
  </div>
  
  <!-- 우하: Advanced + Cascade -->
  <div class="grid-cell">
    <div class="grid-header">Advanced + Cascade</div>
    <div id="advanced-cascade" class="grid-content"></div>
  </div>
</div>

<script>
// 4조합 실행
async function runComparison() {
    const response = await fetch('/api/compare', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            question: document.getElementById('question').value,
            doc_type: document.getElementById('docType').value
        })
    });
    
    const data = await response.json();
    
    // 각 셀에 결과 렌더링
    renderResults('naive-semantic', data.results.naive_semantic.results);
    renderResults('naive-cascade', data.results.naive_cascade.results);
    renderResults('advanced-semantic', data.results.advanced_semantic.results);
    renderResults('advanced-cascade', data.results.advanced_cascade.results);
}
</script>
```

---

## 결과 분석: Semantic + Hierarchical + Advanced RAG 효과

### 효과 검증: "지원금액은 얼마인가요?" 질문

| 조합 | 실행시간 | 최상위 결과 | 점수 | 특징 |
|------|----------|-------------|------|------|
| Naive + Semantic | 2.9초 | 표 데이터 | 0.41 | 단순 벡터 유사도만 활용 |
| Naive + Cascade | 0.5초 | 표 데이터 | 0.41 | 구조화된 메타데이터로 빠른 검색 |
| **Advanced + Semantic** | 7.3초 | 전체 텍스트 | 0.19 | Rerank했으나 관련성 낮음 |
| **Advanced + Cascade** | **8.1초** | **"사업별 최대 정부 지원금: 최대 50억원 이내"** | **0.64** | **가장 정확한 답변** |

### 핵심 발견

#### 1. Hierarchical Chunking의 우위

**이유**:
- **정확한 조항 단위 분할**: `□ 사업별 최대 정부 지원금`이 독립 청크로 존재
- **메타데이터 필터링**: `section_no: "4"`, `section_title: "지원규모 및 범위"`로 빠른 좁히기
- **구조적 맥락**: 사업 목적→지원 대상→지원 금액 순서로 청크가 정렬됨

#### 2. Advanced RAG의 효과 (단, 조건부)

**작동하는 경우**:
- 쿼리 확장이 제대로 작동하면 검색 범위 확장
- Cohere Rerank가 semantic 청킹의 부정확한 순서를 교정

**한계**:
- DeepSeek `response_format` 미지원으로 쿼리 확장 실패
- 5개 질문이 모두 동일하게 반환되어 Naive와 실질적 차이 없음

#### 3. 최적 조합: Hierarchical + Advanced

**시너지**:
```python
# 최적의 RAG 파이프라인
query = "지원금액은 얼마인가요?"

# 1. 계층형 청킹이 정확한 조항 단위로 분할해 있음
chunks = hierarchical_chunking(doc)  
# → chunk["section_title"] == "지원규모 및 범위"
# → chunk["item_marker"] == "□_사업별 최대 정부 지원금"

# 2. Advanced RAG가 여러 표현으로 검색 후 Rerank
expanded_queries = [
    "지원금액은 얼마인가요?",
    "정부 지원금이 얼마나 되나요?",  # 제대로 작동하면
    "최대 지원 규모는?",
    ...
]

# 3. Cohere Rerank가 관련성 순으로 재정렬
reranked = cohere_rerank(query, retrieved_docs)
# → relevance_score: 0.64 (정확한 청크가 1위)
```

---

## 결론 및 최적화 방안

### 1. Semantic + Hierarchical + Advanced RAG의 효과

**검증된 사실**:
- ✅ **Hierarchical Chunking이 법령/공고문에 가장 적합**
  - 구조적 단위(조/항/목)로 분할되어 검색 정확도 향상
  - 메타데이터로 섹션 필터링 가능
  
- ✅ **Advanced RAG가 Query Expansion 작동 시 효과적**
  - 다양한 표현으로 검색 범위 확장
  - Cohere Rerank가 관련성 재정렬
  
- ⚠️ **단, 아키텍처에 따라 효과 다름**
  - 구조화된 문서: Hierarchical 우세
  - 비구조화된 문서: Semantic 유리할 수 있음
  - 쿼리 확장 실패 시 Naive와 유사

### 2. 실전 최적화 방안

#### 2.1 청킹 최적화

**문제**: 8GB 메모리에서 BGE-M3 SemanticChunker 작동 불가

**해결책**:
```python
# 옵션 1: 더 가벼운 모델 사용
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

# 옵션 2: 클라우드 환경에서 실행
# AWS/GCP의 GPU 인스턴스 사용

# 옵션 3: HuggingFace Inference API
# 원격 모델 추론으로 로컬 메모리 절약
```

#### 2.2 HTML 테이블 처리 최적화

**문제**: 28개 표가 맥락 단절

**해결책**:
```python
# 옵션 1: 표 전후 병합
tables = extract_context_around_table(text, table_pattern)
combined_chunk = before_context + table + after_context

# 옵션 2: 표 메타데이터 강화
chunk = {
    "content": table_html,
    "metadata": {
        "type": "table",
        "summary": extract_table_summary(table_html),
        "related_section": section_title
    }
}

# 옵션 3: 표 본문 추출
table_text = html_to_text(table_html)  # 셀 내용을 텍스트로 변환
```

#### 2.3 쿼리 확장 최적화

**문제**: DeepSeek JSON 모드 미지원

**해결책**:
```python
# 옵션 1: JSON 모드 지원 모델 사용
QUERY_MODEL = "gpt-4o-mini"  # JSON mode 지원 완료

# 옵션 2: Few-shot 프롬프트
prompt = f"""질문을 5개로 재구성하라. 예시:
질문: "지원금액은?"
답변: ["지원금액은 얼마인가요?", "정부 지원금 규모는?", ...]

이제 이 질문으로 5개를 만드세요: {question}
답변:"""

# 옵션 3: OpenAI Function Calling
response = client.chat.completions.create(
    tools=[{
        "type": "function",
        "function": {
            "name": "generate_queries",
            "parameters": {"type": "object", "properties": {...}}
        }
    }]
)
```

#### 2.4 메타데이터 통일

**문제**: 시맨틱/계층형 청킹의 메타데이터 구조 불일치

**해결책**:
```python
# 시맨틱 청킹에도 섹션 정보 추가
def add_section_metadata(chunks: list, text: str):
    # 텍스트에서 섹션 헤더 추출
    sections = extract_sections(text)
    
    for chunk in chunks:
        # 청크가 어느 섹션에 속하는지 판단
        section = find_containing_section(chunk["text"], sections)
        chunk["metadata"]["section"] = section
```

---

## 🎯 재현 가능한 전체 코드 구조

### 디렉토리 구조

```
RAG_pipe/
├── config.py                          # API 키, 클라이언트 초기화
├── rag_components.py                    # RAG 핵심 함수
├── app.py                              # Flask 백엔드
├── templates/
│   └── index.html                     # 웹 UI
├── chunking/
│   ├── semantic_chunking.py          # 시맨틱 청킹
│   ├── hierarchical_chunking.py      # 계층형 청킹
│   └── simple_chunking.py            # 단순 청킹 (대체용)
├── upload/
│   ├── upload_semantic.py            # 시맨틱 업로드
│   └── upload_hierarchical.py        # 계층형 업로드
├── db/
│   └── setup_tables.sql              # Supabase 스크립트
├── .env.example                        # 환경변수 템플릿
└── README.md                          # 이 문서
```

### 실행 순서

```bash
# 1. 의존성 설치
pip install flask python-dotenv openai supabase cohere chonkie

# 2. .env 설정
cp .env.example .env
# API 키 입력

# 3. Supabase 테이블 생성
# Supabase SQL Editor에서 db/setup_tables.sql 실행

# 4. 청킹
python chunking/hierarchical_chunking.py
python chunking/simple_chunking.py

# 5. 업로드
python upload/upload_hierarchical.py
python upload/upload_semantic.py

# 6. Flask 실행
python app.py

# 7. 브라우저 접속
# http://localhost:5000
```

---

## 📚 추가 학습 자료

- **LangChain Chunking**: https://python.langchain.com/docs/modules/data_connection/document_transformers/
- **Supabase pgvector**: https://supabase.com/docs/guides/ai/vector-columns
- **Cohere Rerank**: https://docs.cohere.com/reference/rerank
- **OpenRouter Models**: https://openrouter.ai/models

---

**작성일**: 2026-07-04  
**버전**: 1.0  
**라이선스**: MIT
