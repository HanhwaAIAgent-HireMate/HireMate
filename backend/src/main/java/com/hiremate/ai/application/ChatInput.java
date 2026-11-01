package com.hiremate.ai.application;

import com.hiremate.interview.InterviewerRole;
import com.hiremate.recruit.StageStatus;
import com.hiremate.screening.CandidateRow;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/** 권한을 확인하고 모은 Chat 한 번의 입력. 컨트롤러가 스트림을 열기 전에 만든다 ({@link ChatService#prepare}). */
public record ChatInput(UUID companyId, UUID stageId, UUID tabId, UUID memberId, StageStatus status,
        List<CandidateRow> candidates, ChatContext context, Map<UUID, InterviewerRole> interviewerRoles) {

    public ChatInput(UUID companyId, UUID stageId, UUID tabId, UUID memberId, StageStatus status,
            List<CandidateRow> candidates, ChatContext context) {
        this(companyId, stageId, tabId, memberId, status, candidates, context, Map.of());
    }

    /** 면접관 모드의 Chat인가. interviewerRoles는 면접관이 배정된 지원자와 그 지원자에서 맡은 담당이다. */
    public boolean interviewer() {
        return context.interviewer();
    }
}
