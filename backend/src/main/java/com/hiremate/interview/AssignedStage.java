package com.hiremate.interview;

import com.hiremate.recruit.StageStatus;
import java.util.List;
import java.util.UUID;

/**
 * 면접관의 "내 면접" 카드 하나: 내가 지정된 면접 전형.
 *
 * @param roles 내 담당. 한 사람이 두 담당을 함께 맡을 수도 있다
 * @param candidateCount 그 전형의 지원자 수. 시작 전 전형은 0이다
 */
public record AssignedStage(UUID stageId, String stageName, StageStatus status, UUID recruitmentId,
        String recruitmentTitle, List<InterviewerRole> roles, long candidateCount) {
}
