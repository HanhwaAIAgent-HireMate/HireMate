package com.hiremate.apply;

import com.hiremate.posting.DocumentType;
import java.util.UUID;

/** 제출 문서와 추출한 본문. 본문은 문서 Viewer와 분석 근거에 쓴다. */
public record ApplicantDocument(DocumentType type, UUID fileId, String fileName, long size, String text) {
}
