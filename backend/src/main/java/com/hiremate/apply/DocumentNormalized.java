package com.hiremate.apply;

/** 검증한 JSON이 저장됐다. 커밋된 뒤에만 인덱스 작업을 보낸다. */
public record DocumentNormalized(DocumentIndexRequest index) {
}
