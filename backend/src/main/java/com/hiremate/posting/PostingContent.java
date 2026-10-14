package com.hiremate.posting;

import java.util.List;

/** HR이 직접 고치거나 AI 수정 요청으로 고치는 공고 본문. 전형 절차와 필수 제출 서류는 따로 다룬다. */
public record PostingContent(String title, String jobCategory, String employmentType, String career,
        String location, String intro, List<String> duties, List<String> qualifications, List<String> preferred,
        List<String> benefits) {
}
