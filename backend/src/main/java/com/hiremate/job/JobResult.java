package com.hiremate.job;

import java.util.UUID;
import tools.jackson.databind.JsonNode;

/**
 * AI 워커가 Redis 결과 스트림에 넣은 작업 결과.
 *
 * @param result DONE이면 그 경로의 응답 본문, FAILED면 null
 * @param error FAILED의 이유. 로그에만 남기고 화면에는 보이지 않는다
 */
public record JobResult(UUID jobId, String type, String target, JobStatus status, JsonNode result,
        String error) {
}
