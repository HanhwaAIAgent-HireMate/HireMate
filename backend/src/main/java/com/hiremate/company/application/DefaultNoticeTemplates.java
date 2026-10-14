package com.hiremate.company.application;

import com.hiremate.company.NoticeTemplateInfo;
import com.hiremate.company.NoticeTemplateType;

/** 기업이 안내 메일 양식을 등록하기 전에 쓰는 기본 양식. */
public final class DefaultNoticeTemplates {

    private static final String GREETING = "{지원자명}님, {회사명} {공고명} 채용에 지원해 주셔서 감사합니다.";
    private static final String CLOSING = "{회사명} 인사팀 드림";
    private static final String REQUIRED = "본 메일은 발신 전용입니다. 지원자 정보는 채용 목적으로만 이용됩니다.";

    private DefaultNoticeTemplates() {
    }

    public static NoticeTemplateInfo of(NoticeTemplateType type) {
        return switch (type) {
            case NEXT_STAGE -> new NoticeTemplateInfo(type, "[{회사명}] {전형명} 결과 안내", GREETING,
                    "확정 결과 · 다음 전형 정보", CLOSING, REQUIRED);
            case REJECT -> new NoticeTemplateInfo(type, "[{회사명}] {전형명} 결과 안내", GREETING,
                    "확정 결과 · 감사 인사", CLOSING, REQUIRED);
            case FINAL_PASS -> new NoticeTemplateInfo(type, "[{회사명}] 최종 합격 안내", GREETING,
                    "최종 합격 · 입사 안내", CLOSING, REQUIRED);
            case FINAL_REJECT -> new NoticeTemplateInfo(type, "[{회사명}] 최종 결과 안내", GREETING,
                    "최종 결과 · 감사 인사", CLOSING, REQUIRED);
        };
    }
}
