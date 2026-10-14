package com.hiremate.ai.application;

import com.hiremate.apply.ApplicantDocument;
import com.hiremate.company.CompanyProfile;
import com.hiremate.posting.PostingContent;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidateRow;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Root Agent가 받는 요청 범위: 현재 채용 · 전형 + 대상(@멘션 · 체크한 지원자) + 질문 (기획 v7 §10).
 *
 * @param previousTypes 이 전형 앞에 끝난 전형 종류. 아직 없는 자료를 묻는지 판단한다
 * @param documentScores 서류 점수. 평가 결과와 지원서를 맞춰 볼 때 쓴다
 */
public record ChatContext(UUID stageId, String stageName, StageType stageType, List<StageType> previousTypes,
        List<CandidateRow> candidates, Map<UUID, List<ApplicantDocument>> documents,
        Map<UUID, Integer> documentScores, List<UUID> mentions,
        List<UUID> checked, CompanyProfile company, PostingContent posting, String message) {
}
