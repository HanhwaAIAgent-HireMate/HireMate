package com.hiremate.ai.application;

import java.util.UUID;

/** 담당자의 면접 메모. 지원자가 말한 사실이나 평가 결과로 취급하지 않는다. */
public record InterviewerMemo(UUID stageId, String stageName, String text) {
}
