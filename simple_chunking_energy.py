# 분산에너지 공고문 단순 청킹 (BGE-M3 미사용)
# 8GB 메모리 환경을 위한 가벼운 청킹 방식
import json
import re

INPUT_PATH = "2026년_AI기반_분산에너지_특화지역_지원_사업_2차_공고.md"
OUTPUT_PATH = "chunks_energy.jsonl"

CHUNK_SIZE = 1000  # 토큰 수 (대략적)
OVERLAP = 100      # 오버랩

def count_tokens(text: str) -> int:
    """대략적인 토큰 수 계산 (한글 기준)"""
    return len(text) // 3  # 한글은 대략 3자 = 1토큰

print("문서 로드...")
with open(INPUT_PATH, encoding="utf-8") as f:
    text = f.read()

# HTML 표 보존
print("HTML 표 보존 처리...")
tables = re.findall(r"<table>.*?</table>", text, re.DOTALL)
print(f"→ {len(tables)}개 표 발견, placeholder로 치환")

table_map = {}
for i, t in enumerate(tables):
    placeholder = f"\n[[TABLE_{i}]]\n"
    table_map[placeholder] = t
    text = text.replace(t, placeholder, 1)

# 문단 단위로 분할
paragraphs = text.split("\n\n")

chunks = []
current_chunk = ""
chunk_id = 0

for paragraph in paragraphs:
    paragraph = paragraph.strip()
    if not paragraph:
        continue

    # 현재 청크에 추가
    test_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph
    test_tokens = count_tokens(test_chunk)

    if test_tokens > CHUNK_SIZE:
        # 현재 청크 저장
        if current_chunk:
            chunks.append({
                "chunk_id": chunk_id,
                "text": current_chunk.strip(),
                "token_count": count_tokens(current_chunk)
            })
            chunk_id += 1

        # 오버랩 처리
        if OVERLAP > 0:
            words = current_chunk.split()
            overlap_words = words[-OVERLAP:] if len(words) > OVERLAP else words
            current_chunk = " ".join(overlap_words) + "\n\n" + paragraph
        else:
            current_chunk = paragraph
    else:
        current_chunk = test_chunk

# 마지막 청크 저장
if current_chunk:
    chunks.append({
        "chunk_id": chunk_id,
        "text": current_chunk.strip(),
        "token_count": count_tokens(current_chunk)
    })

print(f"생성된 청크 수: {len(chunks)}")

# HTML 표를 별도 청크로 추가
for placeholder, table_html in table_map.items():
    chunks.append({
        "chunk_id": len(chunks),
        "text": table_html.strip(),
        "token_count": count_tokens(table_html)
    })

print(f"총 청크 수 (표 포함): {len(chunks)}")

# 미리보기
print("\n미리보기:")
for i, chunk in enumerate(chunks[:3]):
    preview = chunk["text"][:80].replace("\n", " ")
    print(f"[{i}] (토큰≈{chunk['token_count']}) {preview}")

# JSONL 저장
print("\nJSONL 저장...")
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    for chunk in chunks:
        f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

print(f"저장 완료: {OUTPUT_PATH}")
