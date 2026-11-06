package com.hiremate.company;

/**
 * 안내 메일 양식. 본문은 인사말(greeting) · AI 작성 영역 · 맺음말(closing) 순서이며, 필수 문구(requiredText)는 AI가 바꾸지 않는다.
 * 변수 {지원자명}, {지원번호}, {회사명}, {공고명}, {전형명}은 발송할 때 지원자별로 채운다.
 */
public record NoticeTemplateInfo(NoticeTemplateType type, String subject, String greeting, String aiGuide,
        String closing, String requiredText) {
}
