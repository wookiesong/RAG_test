"""
Advanced RAG 비교 시스템 - 클라이언트 초기화 및 환경변수 설정

이 모듈은 Supabase, OpenAI, Cohere 클라이언트를 초기화하고
필요한 환경변수를 관리합니다.
"""

import os
from dotenv import load_dotenv
load_dotenv()  # .env 파일 로드

from supabase import create_client, Client
from openai import OpenAI
import cohere

# 환경 변수 또는 직접 입력
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kkklbdramtxvtpbxfjpl.supabase.co")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")  # OpenRouter 또는 OpenAI
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# 전역 클라이언트 인스턴스 (lazy initialization)
_supabase_client = None
_openai_client = None
_cohere_client = None
_supabase_key = None

def _get_supabase_key() -> str:
    """Supabase 서비스 롤 키를 가져옵니다 (캐시됨)."""
    global _supabase_key
    if _supabase_key is None:
        key = os.getenv("SUPABASE_KEY")
        if not key:
            print("Supabase 서비스 롤 키를 입력하세요:")
            key = input().strip()
        _supabase_key = key
    return _supabase_key

def get_supabase() -> Client:
    """Supabase 클라이언트 싱글톤을 반환합니다."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, _get_supabase_key())
    return _supabase_client

def get_openai() -> OpenAI:
    """OpenAI 클라이언트 싱글톤을 반환합니다."""
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            print("OpenAI API 키를 입력하세요:")
            key = input().strip()
            _openai_client = OpenAI(api_key=key, base_url=OPENAI_BASE_URL)
        else:
            _openai_client = OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL)
    return _openai_client

def get_cohere() -> cohere.ClientV2:
    """Cohere 클라이언트 싱글톤을 반환합니다."""
    global _cohere_client
    if _cohere_client is None:
        if not COHERE_API_KEY:
            print("Cohere API 키를 입력하세요:")
            key = input().strip()
            _cohere_client = cohere.ClientV2(api_key=key)
        else:
            _cohere_client = cohere.ClientV2(api_key=COHERE_API_KEY)
    return _cohere_client

# 상수 정의
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
QUERY_MODEL = os.getenv("QUERY_MODEL", "gpt-4o-mini")  # .env에서 오버라이드 가능
RERANK_MODEL = "rerank-multilingual-v3.0"
RERANK_TOP_N = 3
MULTI_QUERY_COUNT = 5
RETRIEVE_K = 10

# 테이블 이름
TABLE_SEMANTIC = "documents"
TABLE_CASCADE = "documents_cascade"
TABLE_SEMANTIC_ENERGY = "documents_energy"
TABLE_CASCADE_ENERGY = "documents_energy_cascade"
