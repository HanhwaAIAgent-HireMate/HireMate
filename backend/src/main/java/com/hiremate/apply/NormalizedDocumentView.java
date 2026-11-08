package com.hiremate.apply;

import com.hiremate.posting.DocumentType;

/**
 * 화면에 보여 줄 정제 문서(서류 원문). 정제를 마친 서류만 준다. 블라인드 채용이면 본문과 같은 규칙으로 지원자 이름을 가린다.
 * 화면은 이 JSON을 그대로 표 · 목록으로 그리고 글자를 바꾸거나 빼지 않는다.
 */
public record NormalizedDocumentView(DocumentType type, NormalizedDocument document) {
}
