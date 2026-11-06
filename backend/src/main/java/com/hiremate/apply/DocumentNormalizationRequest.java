package com.hiremate.apply;

import com.hiremate.posting.DocumentType;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

/** 기업과 문서 버전 범위가 고정된 정제 요청. */
public record DocumentNormalizationRequest(UUID companyId, UUID recruitmentId, UUID applicationId,
                                            UUID documentId, int revision, DocumentType documentType,
                                            List<DocumentSource> sources) {
    public DocumentNormalizationRequest {
        Objects.requireNonNull(companyId);
        Objects.requireNonNull(recruitmentId);
        Objects.requireNonNull(applicationId);
        NormalizedDocument.validateMetadata(documentId, revision, documentType);
        sources = List.copyOf(sources);
        var ids = new HashSet<String>();
        for (DocumentSource source : sources) {
            if (!ids.add(source.id())) {
                throw new IllegalArgumentException("Duplicate source ID");
            }
        }
    }
}
