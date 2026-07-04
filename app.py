#!/usr/bin/env python3
"""
Flask 백엔드 - 분산에너지 RAG 비교 시스템

2×2 그리드 (시맨틱/계층형 × Naive/Advanced) 실시간 비교를 위한 API 제공
"""

import os
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

from rag_components import run_all_combos
from config import QUERY_MODEL, TABLE_SEMANTIC, TABLE_CASCADE, TABLE_SEMANTIC_ENERGY, TABLE_CASCADE_ENERGY

app = Flask(__name__)

# 테이블 매핑
TABLE_PAIRS = {
    "civil": (TABLE_SEMANTIC, TABLE_CASCADE),
    "energy": (TABLE_SEMANTIC_ENERGY, TABLE_CASCADE_ENERGY),
}

# 모델 리스트 (.env에서 가져오기, 기본값 설정)
LLM_MODELS = os.getenv("LLM_MODELS", "deepseek/deepseek-chat-v3.1,gpt-4o-mini").split(",")


@app.route("/")
def index():
    """메인 페이지 렌더링"""
    return render_template("index.html")


@app.route("/api/config")
def get_config():
    """프론트엔드용 설정 정보 반환"""
    return jsonify({
        "default_model": QUERY_MODEL,
        "llm_models": LLM_MODELS,
        "doc_types": [
            {"value": "civil", "label": "민원처리법"},
            {"value": "energy", "label": "분산에너지 공고"}
        ]
    })


@app.route("/api/compare", methods=["POST"])
def compare():
    """4조합 RAG 실행 및 결과 반환"""
    try:
        data = request.get_json()
        question = data.get("question", "").strip()
        doc_type = data.get("doc_type", "civil")
        query_model = data.get("query_model")  # 선택적 모델 오버라이드

        if not question:
            return jsonify({"error": "질문을 입력해주세요"}), 400

        if doc_type not in TABLE_PAIRS:
            return jsonify({"error": f"지원하지 않는 문서 유형: {doc_type}"}), 400

        # 테이블 쌍 선택
        table_semantic, table_cascade = TABLE_PAIRS[doc_type]

        # 모델 오버라이드 (선택적)
        if query_model:
            from config import _openai_client
            import tempfile
            import json

            # 임시로 QUERY_MODEL 변경 (런타임)
            from rag_components import QUERY_MODEL as CURRENT_QUERY_MODEL
            original_model = CURRENT_QUERY_MODEL

            # 런타임 모델 변경을 위해 환경변수 임시 설정
            os.environ["QUERY_MODEL"] = query_model

            # rag_components 모듈 리로드 (새 QUERY_MODEL 적용)
            import importlib
            import rag_components
            importlib.reload(rag_components)

            try:
                results = rag_components.run_all_combos(question, table_semantic, table_cascade)
            finally:
                # 원복
                if original_model:
                    os.environ["QUERY_MODEL"] = original_model
        else:
            results = run_all_combos(question, table_semantic, table_cascade)

        # 결과 변환 (JSON 직렬화를 위해)
        serializable_results = {}
        for key, value in results.items():
            serializable_results[key] = {
                "results": value.get("results", []),
                "execution_time": value.get("execution_time", 0),
                "method": value.get("method", ""),
                "table": value.get("table", ""),
                "retrieved_count": value.get("retrieved_count", 0)
            }
            # Advanced RAG의 추가 필드
            if "expanded_queries" in value:
                serializable_results[key]["expanded_queries"] = value["expanded_queries"]
            if "timing" in value:
                serializable_results[key]["timing"] = value["timing"]

        return jsonify({
            "success": True,
            "question": question,
            "doc_type": doc_type,
            "results": serializable_results
        })

    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"Starting Flask server on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
