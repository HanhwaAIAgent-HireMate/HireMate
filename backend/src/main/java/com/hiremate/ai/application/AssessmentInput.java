package com.hiremate.ai.application;

import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;

/**
 * 지원자 한 명의 평가 결과. 점수 · 등급은 assessment 모듈이 저장한 값 그대로이고 AI는 바꾸지 않는다.
 *
 * @param areas 영역 이름을 키로 쓴 점수. 점수가 없는 영역은 null이다
 * @param submission 평가 전형에 올린 PDF(결과 리포트, 과제 제출물)와 추출한 본문. 파일을 올리지 않았으면 null
 * @param url 과제 제출 URL. ai 서버는 주소만 받고 본문을 가져오지 않는다
 * @param note HR이 남긴 평가 메모
 */
public record AssessmentInput(UUID companyId, UUID recruitmentId, UUID stageId, UUID applicationId,
        String stageName, BigDecimal total, Map<String, BigDecimal> areas, String grade, Submission submission,
        String url, String note) {

    public record Submission(String fileName, String text) {
    }
}
