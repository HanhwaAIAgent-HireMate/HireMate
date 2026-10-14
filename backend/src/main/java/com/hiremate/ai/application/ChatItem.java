package com.hiremate.ai.application;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.UUID;

/**
 * 답변의 한 줄. 예: "정유민 — 카드 결제 승인 · 정산 4년".
 *
 * @param status OK는 근거 충분, CHECK는 확인 필요, 없으면 null
 */
public record ChatItem(@Schema(nullable = true) UUID applicationId, String label, String text,
        @Schema(nullable = true) String status) {
}
