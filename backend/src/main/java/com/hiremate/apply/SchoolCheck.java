package com.hiremate.apply;

import com.hiremate.posting.DocumentType;
import java.util.List;

/**
 * 블라인드 채용 지원서에서 찾은 학교 이름. 제출 전에 지원자에게 알려 다시 올리거나 그대로 내게 한다.
 * 블라인드가 아니거나 찾은 이름이 없으면 documents가 비어 있다.
 */
public record SchoolCheck(List<Found> documents) {

    public record Found(DocumentType type, List<String> names) {
    }
}
