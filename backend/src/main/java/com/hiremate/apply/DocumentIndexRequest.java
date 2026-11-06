package com.hiremate.apply;

import java.util.Objects;

/** backend에 저장한 정제 문서와 그 문서에 사용한 범위를 함께 인덱서에 전달한다. */
public record DocumentIndexRequest(DocumentNormalizationRequest request, NormalizedDocument document) {
    public DocumentIndexRequest {
        Objects.requireNonNull(request);
        Objects.requireNonNull(document);
        if (!request.documentId().equals(document.documentId()) || request.revision() != document.revision()
                || request.documentType() != document.documentType()) {
            throw new IllegalArgumentException("Normalized document identity does not match its request");
        }
        document.validateSources(request.sources());
    }
}
