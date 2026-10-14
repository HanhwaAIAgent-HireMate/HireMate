/**
 * AI 서버(ai/) 연동. AI 서버 호출, Chat 스트리밍(SSE) 중계, 공고 · 안내 · 질문 · 리포트 초안 요청.
 *
 * <p>AI가 보낸 선택 편집 명령은 screening 모듈에 실행을 맡긴다. 지원자 상태를 직접 바꾸지 않는다.
 */
package com.hiremate.ai;
