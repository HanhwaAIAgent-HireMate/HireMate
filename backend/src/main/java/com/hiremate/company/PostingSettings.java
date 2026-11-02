package com.hiremate.company;

import java.util.List;

/** 채용 공고 설정. Posting Agent의 작성 스타일, 모든 공고에 들어가는 필수 안내 문구. */
public record PostingSettings(String writingStyle, List<String> requiredNotices) {
}
