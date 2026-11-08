package com.hiremate.apply;

import java.util.UUID;

/** AI 워커의 문서 색인 결과. */
public record DocumentIndexResult(UUID documentId, int revision, String status) {
}
