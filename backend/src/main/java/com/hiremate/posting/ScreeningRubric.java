package com.hiremate.posting;

import java.util.List;
import java.util.UUID;

/**
 * 서류 평가 기준. 우대 사항마다 사람이 정한 가중치(1~5)와 평가 조건을 담은 NCS 능력단위, 선발 인원을 둔다.
 * 공고 작성 화면에서 입력하기 전까지는 설정(hiremate.dummy.screening-rubric)의 더미를 모든 채용에 쓴다.
 *
 * @param hireCount 선발 인원. 서류 전형의 AI 추천은 이 인원의 10배수까지다
 * @param preferred 공고 본문의 우대 사항과 같은 글이어야 짝이 맞는다
 */
public record ScreeningRubric(UUID companyId, UUID recruitmentId, int hireCount, List<Preference> preferred) {

    /**
     * @param ncsUnitCode NCS 능력단위코드 (예: 2001020218_23v6)
     * @param certificates 이 능력과 관련된 자격증. AI 적합도의 '자격증 · 학습' 항목에서 본다
     */
    public record Preference(String text, int weight, String ncsUnitCode, List<String> certificates) {
    }
}
