package com.hiremate.ai.application;

import io.swagger.v3.oas.annotations.media.Schema;
import java.util.List;
import java.util.UUID;

/**
 * 지원자 카드의 프로필 탭 (STG-06). 분석 Agent(지원서 · 평가 · 면접)가 쌓은 프로필 항목을 확인 상태와 함께 보여 준다
 * (NFR-03: 확인된 사실과 AI 해석을 구분한다). ai 서버의 지원자 프로필(ai 스키마)을 읽어 온다.
 *
 * @param status 프로필 분석 상태. 프로필이 아직 없으면 null
 * @param items 저장된 순서의 프로필 항목
 */
public record CandidateProfileView(UUID applicationId, @Schema(nullable = true) Status status, String summary,
        List<ProfileItemView> items) {

    /** 프로필이 아직 없는 지원자. */
    public static CandidateProfileView empty(UUID applicationId) {
        return new CandidateProfileView(applicationId, null, "", List.of());
    }

    /** 프로필 분석 상태: 분석 완료 · 확인 필요(근거 부족) · 분석 실패. */
    public enum Status {
        DONE, CHECK, FAILED
    }

    /** 항목의 확인 상태: 확인됨(평가 · 면접에서 확인) · 근거 있음 · 미확인(근거 없음) · 상충(자료끼리 어긋남). */
    public enum Verification {
        CONFIRMED, EVIDENCED, UNCONFIRMED, CONFLICT
    }

    /**
     * 프로필 항목 한 줄.
     *
     * @param category 분류 (EXPERIENCE · DOMAIN · SKILL · QUALIFICATION · COMPANY_FIT · STRENGTH · CHECK)
     * @param agent 항목을 만든 분석 Agent (application · assessment · interview)
     * @param evidence 원문 근거 문장. 없으면 null
     * @param stageId 평가 · 면접 항목이면 그 전형. 지원서 항목은 null
     */
    public record ProfileItemView(String category, String agent, String content,
            @Schema(nullable = true) String evidence, String source, Verification verification,
            @Schema(nullable = true) UUID stageId) {
    }
}
