package com.hiremate.ai.application;

import java.util.UUID;

/** Chat 질문에 쓴 @멘션 지원자. */
public record ChatMention(UUID applicationId, String name) {
}
