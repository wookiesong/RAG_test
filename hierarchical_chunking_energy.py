# 분산에너지 공고문 계층형 청킹
import re
import json
from pathlib import Path

INPUT_PATH = Path("2026년_AI기반_분산에너지_특화지역_지원_사업_2차_공고.md")
OUTPUT_PATH = Path("chunks_energy_cascade.jsonl")

print("=" * 80)
print("분산에너지 공고문 계층형 청킹")
print("=" * 80)

print(f"\n입력 파일: {INPUT_PATH}")
print(f"파일 존재 여부: {INPUT_PATH.exists()}")

if not INPUT_PATH.exists():
    print("오류: 입력 파일을 찾을 수 없습니다.")
    exit(1)

# 1. 문서 읽기
print("\n문서 읽기...")
with open(INPUT_PATH, encoding="utf-8") as f:
    raw_text = f.read()

# HTML 표 보존 전처리
print("HTML 표 보존 처리...")
tables = re.findall(r"<table>.*?</table>", raw_text, re.DOTALL)
print(f"→ {len(tables)}개 표 발견, placeholder로 치환")

# 표를 placeholder로 치환
table_map = {}
for i, t in enumerate(tables):
    placeholder = f"\n[[TABLE_{i}]]\n"
    table_map[placeholder] = t
    raw_text = raw_text.replace(t, placeholder, 1)  # 첫 번째 발생만 치환

lines = raw_text.splitlines()
print(f"총 줄 수: {len(lines)}")

# 2. 문서 구조 확인 (처음 40줄)
print("\n" + "=" * 80)
print("문서 구조 확인 (처음 40줄):")
print("=" * 80)
for i, line in enumerate(lines[:40], start=1):
    print(f"{i:03d}: {line}")

# 3. 공고문 전용 정규식 패턴
print("\n" + "=" * 80)
print("정규식 패턴 설계:")
print("=" * 80)

# 섹션 패턴: | N | 섹션명 |
section_pattern = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*$")

# 항목 패턴: □ 항목명
item_pattern = re.compile(r"^□\s*(.+?)$")

# 한글 음절 패턴: 가. 나. 다.
syl_pattern = re.compile(r"^([가-힣])\.\s*(.+)$")

# 원번호 패턴: ①②③④⑤
number_pattern = re.compile(r"^([①-⑳])\s*(.+)$")

# 서브 항목 패턴: ㅇ
subitem_pattern = re.compile(r"^ㅇ\s+(.+)$")

# 주석 패턴: ※
note_pattern = re.compile(r"^※\s+(.+)$")

print("정규식 준비 완료")

# 4. 정규식 테스트
print("\n" + "=" * 80)
print("정규식 테스트:")
print("=" * 80)

sample_lines = [
    "| 1 | 사업개요 |",
    "□ 사업목적",
    "가. 지원대상",
    "① 신청자격",
    "ㅇ 서브항목",
    "※ 비고사항",
]

for s in sample_lines:
    print(f"\n원문: {s}")

    for name, pattern in [
        ("section", section_pattern),
        ("item", item_pattern),
        ("syl", syl_pattern),
        ("number", number_pattern),
        ("subitem", subitem_pattern),
        ("note", note_pattern),
    ]:
        m = pattern.match(s)
        if m:
            print(f"  {name} => {m.groups()}")

# 5. 현재 상태 저장 방식
def build_source_path(doc_title, section_no, section_title, item_marker, subsection):
    """출처 경로 문자열을 만든다."""
    parts = [doc_title]
    if section_no:
        parts.append(f"섹션{section_no}_{section_title}")
    if item_marker:
        parts.append(f"항목_{item_marker}")
    if subsection:
        parts.append(subsection)
    return " > ".join(parts)

# 6. 항목 저장 함수
def save_current_item(chunks, current_item):
    """현재 항목을 chunks 리스트에 저장한다."""
    if current_item is None:
        return

    content = "\n".join(current_item["content_lines"]).strip()

    if not content:
        return

    source_path = build_source_path(
        doc_title=current_item["doc_title"],
        section_no=current_item["section_no"],
        section_title=current_item["section_title"],
        item_marker=current_item["item_marker"],
        subsection=current_item["subsection"],
    )

    chunk = {
        "chunk_id": len(chunks) + 1,
        "doc_title": current_item["doc_title"],
        "section_no": current_item["section_no"],
        "section_title": current_item["section_title"],
        "item_marker": current_item["item_marker"],
        "subsection": current_item["subsection"],
        "content": content,
        "source_path": source_path,
        "doc_type": "energy",
        "notice_no": "2026-642",
    }

    chunks.append(chunk)

# 7. 계층형 청킹 함수
def hierarchical_chunk_notice(md_text):
    doc_title = "2026년 AI기반 분산에너지 특화지역 지원 사업 2차 공고"
    current_section_no = None
    current_section_title = None
    current_item = None

    chunks = []

    for line in md_text.splitlines():
        stripped = line.strip()

        # 빈 줄 처리
        if not stripped:
            if current_item is not None:
                current_item["content_lines"].append("")
            continue

        # 1. 섹션 패턴: | N | 섹션명 |
        m = section_pattern.match(stripped)
        if m:
            save_current_item(chunks, current_item)
            current_item = None

            current_section_no = m.group(1).strip()
            current_section_title = m.group(2).strip()
            continue

        # 2. 항목 패턴: □ 항목명
        m = item_pattern.match(stripped)
        if m:
            save_current_item(chunks, current_item)

            item_marker = f"□_{m.group(1).strip()}"
            subsection = None

            current_item = {
                "doc_title": doc_title,
                "section_no": current_section_no,
                "section_title": current_section_title,
                "item_marker": item_marker,
                "subsection": subsection,
                "content_lines": [],
            }
            continue

        # 3. 한글 음절 패턴: 가. 나.
        m = syl_pattern.match(stripped)
        if m and current_item is not None:
            # 새로운 하위 항목이므로 현재 항목 저장 후 새로 시작
            save_current_item(chunks, current_item)

            subsection = f"{m.group(1)}.{m.group(2).strip()}"
            current_item = {
                "doc_title": doc_title,
                "section_no": current_section_no,
                "section_title": current_section_title,
                "item_marker": current_item["item_marker"] if current_item else None,
                "subsection": subsection,
                "content_lines": [],
            }
            continue

        # 4. 원번호 패턴: ①②③
        m = number_pattern.match(stripped)
        if m and current_item is not None:
            save_current_item(chunks, current_item)

            subsection = f"{m.group(1)}_{m.group(2).strip()}"
            current_item = {
                "doc_title": doc_title,
                "section_no": current_section_no,
                "section_title": current_section_title,
                "item_marker": current_item["item_marker"] if current_item else None,
                "subsection": subsection,
                "content_lines": [],
            }
            continue

        # 5. 주석 패턴: ※ (별도 청크로 저장하지 않고 직전 항목에 병합)
        m = note_pattern.match(stripped)
        if m and current_item is not None:
            # 주석을 현재 항목의 끝에 추가
            current_item["content_lines"].append(f"※ {m.group(1).strip()}")
            continue

        # 6. 일반 본문
        if current_item is not None:
            current_item["content_lines"].append(stripped)

    # 마지막 항목 저장
    save_current_item(chunks, current_item)

    # HTML 표를 별도 청크로 저장
    for placeholder, table_html in table_map.items():
        chunks.append({
            "chunk_id": len(chunks) + 1,
            "doc_title": doc_title,
            "section_no": None,
            "section_title": "HTML_표",
            "item_marker": "TABLE",
            "subsection": None,
            "content": table_html.strip(),
            "source_path": f"{doc_title} > HTML_표",
            "doc_type": "energy",
            "notice_no": "2026-642",
        })

    return chunks

# 8. 청킹 실행
print("\n" + "=" * 80)
print("계층형 청킹 실행...")
print("=" * 80)

chunks = hierarchical_chunk_notice(raw_text)
print(f"생성된 청크 수: {len(chunks)}")

# 앞의 3개 청크 확인
print("\n앞의 3개 청크 확인:")
for chunk in chunks[:3]:
    print("-" * 80)
    print(f"chunk_id: {chunk['chunk_id']}")
    print(f"source_path: {chunk['source_path']}")
    print(f"item_marker: {chunk.get('item_marker', 'N/A')}")
    print(f"content preview: {chunk['content'][:200]}")

# 9. JSONL 저장
print("\n" + "=" * 80)
print(f"JSONL 저장: {OUTPUT_PATH}")
print("=" * 80)

with OUTPUT_PATH.open("w", encoding="utf-8") as f:
    for chunk in chunks:
        f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

print(f"저장 완료: {OUTPUT_PATH}")
print("=" * 80)
