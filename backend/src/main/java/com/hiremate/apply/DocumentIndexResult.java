package com.hiremate.apply;

import java.util.Set;
import java.util.UUID;

/** 워커가 처리한 문서와 수락된 정리 버전을 식별한다. */
public record DocumentIndexResult(UUID documentId, int revision, String status) {
    public DocumentIndexResult {
        if (documentId == null || revision < 1 || status == null
                || !Set.of("INDEXED", "UNCHANGED", "STALE").contains(status)) {
            throw new IllegalArgumentException("Invalid document index result");
        }
    }
}
