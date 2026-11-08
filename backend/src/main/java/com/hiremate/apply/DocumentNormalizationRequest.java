package com.hiremate.apply;

import com.hiremate.file.PdfText;
import com.hiremate.posting.DocumentType;
import java.util.List;
import java.util.UUID;

/** 정제 대상과 Java PDF 파서가 추출한 페이지 정보. */
public record DocumentNormalizationRequest(UUID companyId, UUID recruitmentId, UUID applicationId,
        UUID documentId, int revision, DocumentType documentType, List<PdfText.Page> pages) {
    public DocumentNormalizationRequest {
        NormalizedDocument.validateMetadata(documentId, revision, documentType);
        pages = List.copyOf(pages);
    }
}
