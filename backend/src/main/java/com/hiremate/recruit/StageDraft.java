package com.hiremate.recruit;

/** 공고에서 정한 전형 하나. 이름은 기업이 부르는 그대로 쓴다. */
public record StageDraft(String name, StageType type) {
}
