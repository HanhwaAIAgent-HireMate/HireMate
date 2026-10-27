package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDocument;
import com.hiremate.company.CompanyProfile;
import com.hiremate.interview.InterviewView;
import com.hiremate.posting.PostingContent;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidateRow;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Root Agent가 받는 요청 범위: 현재 채용 · 전형 + 대상(@멘션 · 체크한 지원자) + 질문 (기획 v7 §10).
 *
 * @param recruitmentId 조회 범위. ai 서버의 도구가 지원자 프로필을 이 채용 안에서만 찾는다
 * @param threadId 대화방. 기업 · 전형 · 담당자로 만든다 (기업:전형:담당자). 끝난 전형이면 비워 대화를 남기지 않는다
 * @param selectable 선택 지원자를 바꿀 수 있는가. 진행 중인 전형만 true다
 * @param stages 채용의 전형 전체를 순서대로. 현재 전형도 들어 있다. 아직 진행하지 않은 전형의 자료를 없는 자료와 나눈다
 * @param documentScores 서류 점수. 평가 결과와 지원서를 맞춰 볼 때 쓴다
 * @param interviews 면접 전형이면 지원자별 현재 · 이전 면접 질문과 답변, 아니면 비어 있다
 */
public record ChatContext(UUID stageId, UUID recruitmentId, String threadId, String stageName, boolean selectable,
        StageType stageType,
        List<Stage> stages,
        List<CandidateRow> candidates, Map<UUID, List<ApplicantDocument>> documents,
        Map<UUID, BigDecimal> documentScores, Map<UUID, InterviewView> interviews, List<UUID> mentions,
        List<UUID> checked, CompanyProfile company, PostingContent posting, String message,
        Map<UUID, List<InterviewerMemo>> interviewerMemos) {

    public ChatContext(UUID stageId, UUID recruitmentId, String threadId, String stageName, boolean selectable,
            StageType stageType, List<Stage> stages, List<CandidateRow> candidates,
            Map<UUID, List<ApplicantDocument>> documents, Map<UUID, BigDecimal> documentScores,
            Map<UUID, InterviewView> interviews, List<UUID> mentions, List<UUID> checked,
            CompanyProfile company, PostingContent posting, String message) {
        this(stageId, recruitmentId, threadId, stageName, selectable, stageType, stages, candidates,
                documents, documentScores, interviews, mentions, checked, company, posting, message, Map.of());
    }

    /** 채용의 전형 하나. */
    public record Stage(UUID id, String name, StageType type, StageStatus status) {
    }
}
