package com.hiremate.recruit;

import io.swagger.v3.oas.annotations.media.Schema;

/** 공고에서 정한 전형 하나. 이름은 기업이 부르는 그대로 쓴다. */
public record StageDraft(String name, StageType type,
        @Schema(nullable = true, requiredMode = Schema.RequiredMode.NOT_REQUIRED) StageIcon icon) {
    public StageDraft(String name, StageType type) {
        this(name, type, null);
    }
}
