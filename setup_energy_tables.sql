-- 분산에너지 공고문용 Supabase 테이블 및 RPC 함수 생성
-- Supabase SQL Editor에서 실행하세요

-- 1. documents_energy 테이블 생성 (시맨틱 청킹용)
CREATE TABLE documents_energy (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  content text,
  metadata jsonb,
  embedding vector(1536)
);

-- 2. documents_energy_cascade 테이블 생성 (계층형 청킹용)
CREATE TABLE documents_energy_cascade (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  content text,
  metadata jsonb,
  embedding vector(1536)
);

-- 3. match_documents_energy RPC 함수 생성
CREATE OR REPLACE FUNCTION match_documents_energy (
  query_embedding vector(1536),
  match_count int DEFAULT 10,
  filter jsonb DEFAULT '{}'
) RETURNS TABLE (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
BEGIN
  RETURN QUERY
  SELECT
    id,
    content,
    metadata,
    1 - (embedding <=> query_embedding) AS similarity
  FROM documents_energy
  WHERE metadata @> filter
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 4. match_documents_energy_cascade RPC 함수 생성
CREATE OR REPLACE FUNCTION match_documents_energy_cascade (
  query_embedding vector(1536),
  match_count int DEFAULT 10,
  filter jsonb DEFAULT '{}'
) RETURNS TABLE (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $$
#variable_conflict use_column
BEGIN
  RETURN QUERY
  SELECT
    id,
    content,
    metadata,
    1 - (embedding <=> query_embedding) AS similarity
  FROM documents_energy_cascade
  WHERE metadata @> filter
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- 5. 생성 완료 확인
SELECT 'documents_energy 테이블 생성 완료' as status
UNION ALL
SELECT 'documents_energy_cascade 테이블 생성 완료' as status
UNION ALL
SELECT 'match_documents_energy 함수 생성 완료' as status
UNION ALL
SELECT 'match_documents_energy_cascade 함수 생성 완료' as status;
