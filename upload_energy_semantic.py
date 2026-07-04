import os
import json
from dotenv import load_dotenv
load_dotenv()  # .env 파일 로드

from supabase import create_client, Client
from openai import OpenAI

# 환경 변수 또는 직접 입력
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://kkklbdramtxvtpbxfjpl.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # 서비스 롤 키
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # OpenAI API 키

# API 키 확인
if not SUPABASE_KEY:
    print("Supabase 서비스 롤 키를 입력하세요:")
    SUPABASE_KEY = input().strip()

if not OPENAI_API_KEY:
    print("OpenAI API 키를 입력하세요:")
    OPENAI_API_KEY = input().strip()

# Supabase 클라이언트 초기화
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# OpenAI 클라이언트 초기화
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# chunks_energy.jsonl 파일 읽기
CHUNKS_FILE = "chunks_energy.jsonl"

print(f"{CHUNKS_FILE} 파일 읽기...")
chunks = []
with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
    for line in f:
        chunks.append(json.loads(line))

print(f"총 {len(chunks)}개 청크 로드 완료")

# OpenAI embedding-small 모델로 임베딩 생성
print("\nOpenAI text-embedding-3-small 모델로 임베딩 생성 중...")
MODEL_NAME = "text-embedding-3-small"

# 배치로 임베딩 생성 (최대 2048개)
batch_size = 100
embeddings = []

for i in range(0, len(chunks), batch_size):
    batch = chunks[i:i+batch_size]
    texts = [chunk["text"] for chunk in batch]

    response = openai_client.embeddings.create(
        input=texts,
        model=MODEL_NAME
    )

    batch_embeddings = [item.embedding for item in response.data]
    embeddings.extend(batch_embeddings)

    print(f"  진행률: {min(i+batch_size, len(chunks))}/{len(chunks)}")

print(f"임베딩 생성 완료 (차원: {len(embeddings[0])})")

# Supabase에 삽입
print("\nSupabase documents_energy 테이블에 삽입 중...")

records = []
for i, chunk in enumerate(chunks):
    record = {
        # id 제거 - Supabase가 자동 생성
        "content": chunk["text"],
        "metadata": {
            "token_count": chunk["token_count"],
            "source": "2026년_AI기반_분산에너지_특화지역_지원_사업_2차_공고.md"
        },
        "embedding": embeddings[i]
    }
    records.append(record)

# 배치 삽입 (Supabase는 한 번에 최대 100개)
for i in range(0, len(records), 100):
    batch = records[i:i+100]
    try:
        result = supabase.table("documents_energy").insert(batch).execute()
        print(f"  삽입 완료: {i+1}-{min(i+100, len(records))} ({len(result.data)}개)")
    except Exception as e:
        print(f"  삽입 실패 ({i+1}-{min(i+100, len(records))}): {e}")
        # 개별 삽입 시도
        for j, record in enumerate(batch):
            try:
                supabase.table("documents_energy").insert(record).execute()
            except Exception as e2:
                print(f"    개별 실패 ID {record['id']}: {e2}")

print(f"\n완료! 총 {len(records)}개 문서가 Supabase documents_energy 테이블에 저장되었습니다.")
