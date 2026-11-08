"""NCS 참고 검색. 직무 자료 묶음을 ai DB에 적재하고 pgvector로 찾는다.

요청 문장의 임베딩은 이 패키지의 서비스(`uv run --group ncs python -m hiremate_ai.ncs_search`)가 따로 띄워 맡는다.
묶음의 벡터는 이미 만든 BGE-M3 벡터를 옮겨 쓰고 다시 임베딩하지 않는다.
"""
