package com.hiremate.apply;

import java.util.Objects;

/** 블라인드 처리한 파서 원문 조각. */
public record DocumentSource(String id, Integer page, String text) {
    public DocumentSource {
        Objects.requireNonNull(id);
        Objects.requireNonNull(text);
        if (id.isBlank() || (page != null && page < 1)) {
            throw new IllegalArgumentException("Invalid source ID or page");
        }
    }
}
