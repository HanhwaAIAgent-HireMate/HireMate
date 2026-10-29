package com.hiremate.ai.application;

import java.util.UUID;

/** 질문한 담당자. 탭 대화방은 같은 기업 담당자가 함께 써서 턴마다 남긴다. 결정자 이름처럼 이름을 복사해 둔다. */
public record ChatAsker(UUID memberId, String name) {
}
