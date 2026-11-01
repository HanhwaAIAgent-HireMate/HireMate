package com.hiremate.interview;

import io.swagger.v3.oas.annotations.media.Schema;
import java.time.Instant;
import java.util.UUID;

/**
 * 면접관 의견 한 칸. 배정된 담당마다 하나씩 보이고, 아직 쓰지 않았으면 submitted가 false다.
 * 면접관에게는 내 의견을 저장하기 전까지 다른 면접관 의견의 recommendation · comment를 비워 보낸다.
 *
 * @param mine 요청한 계정의 의견 칸인가
 * @param edited 처음 저장한 뒤 고쳤나
 * @param unassigned 의견을 쓴 뒤 배정이 바뀐 면접관의 의견인가
 */
public record OpinionView(UUID memberId, String name, InterviewerRole role, boolean submitted,
        @Schema(nullable = true) Recommendation recommendation, @Schema(nullable = true) String comment,
        @Schema(nullable = true) Instant updatedAt, boolean edited, boolean mine, boolean unassigned) {
}
