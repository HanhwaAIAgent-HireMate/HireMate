package com.hiremate.apply;

import com.hiremate.posting.DocumentType;
import java.util.UUID;

/**
 * 제출 문서와 본문. 본문은 문서 Viewer와 분석 근거에 쓴다. 정제를 마친 서류는 정제 문서를 펼친 글이고(NormalizedDocument.readingText),
 * 정제 전이거나 정제에 실패한 서류는 PDF에서 추출한 글이다. AI Agent(서류 분석, 면접 질문, Chat)는 모두 이 본문을 읽는다.
 */
public record ApplicantDocument(DocumentType type, UUID fileId, String fileName, long size, String text) {
}
