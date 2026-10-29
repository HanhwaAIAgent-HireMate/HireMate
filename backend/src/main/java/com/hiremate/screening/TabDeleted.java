package com.hiremate.screening;

import java.util.UUID;

/** 전형 화면의 탭을 지웠다. AI Chat 대화방 지우기가 이 이벤트를 받는다. */
public record TabDeleted(UUID companyId, UUID stageId, UUID tabId) {
}
