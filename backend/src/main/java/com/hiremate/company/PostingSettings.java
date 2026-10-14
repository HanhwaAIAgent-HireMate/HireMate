package com.hiremate.company;

import java.util.List;

/** 채용 공고 설정. 새 공고의 Template 순서, Posting Agent의 작성 스타일, 모든 공고에 들어가는 필수 안내 문구. */
public record PostingSettings(List<String> sections, String writingStyle, List<String> requiredNotices) {

    /** 공고 Template의 섹션 순서. 새 공고가 이 순서로 열린다. */
    public static final List<String> SECTIONS =
            List.of("회사 소개", "주요 업무", "자격 요건", "우대 사항", "전형 절차", "필수 제출 서류", "복지", "유의사항");
}
