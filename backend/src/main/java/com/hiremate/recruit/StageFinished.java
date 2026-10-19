package com.hiremate.recruit;

import java.util.UUID;

/** 전형을 종료했다. AI Chat 대화방 지우기가 이 이벤트를 받는다. */
public record StageFinished(UUID stageId, UUID companyId) {
}
