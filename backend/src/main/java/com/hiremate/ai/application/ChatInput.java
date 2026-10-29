package com.hiremate.ai.application;

import com.hiremate.recruit.StageStatus;
import com.hiremate.screening.CandidateRow;
import java.util.List;
import java.util.UUID;

/** 권한을 확인하고 모은 Chat 한 번의 입력. 컨트롤러가 스트림을 열기 전에 만든다 ({@link ChatService#prepare}). */
public record ChatInput(UUID companyId, UUID stageId, UUID tabId, StageStatus status, List<CandidateRow> candidates,
        ChatContext context) {
}
