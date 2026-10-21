package com.hiremate.job;

import java.util.UUID;
import tools.jackson.databind.JsonNode;

/**
 * AI 워커가 처리할 분석 작업. Redis 작업 스트림에 넣는다.
 *
 * @param type ai 서버 경로와 같은 '{agent}/{method}' (예: application/analyze)
 * @param target 작업 대상 (application/analyze면 지원서 ID). 같은 대상의 작업을 묶는 데 쓴다
 * @param payload 그 경로의 요청 본문. Agent 메서드의 매개변수 이름을 키로 한 JSON 객체다
 */
public record Job(UUID jobId, String type, String target, JsonNode payload) {
}
