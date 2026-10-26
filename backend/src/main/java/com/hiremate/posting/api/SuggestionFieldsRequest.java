package com.hiremate.posting.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * 수정안에서 적용하거나 되돌릴 칸. 화면은 공고의 덩어리(기본 정보, 회사 소개, 주요 업무, 자격 요건 …)마다 보낸다.
 *
 * @param fields 수정안의 changedFields에 있는 칸 이름 (예: preferred, stages, requiredDocuments)
 */
public record SuggestionFieldsRequest(@Size(max = 20) List<@NotBlank @Size(max = 50) String> fields) {

    /** 본문이나 칸이 없으면 빈 목록이다 (수정안 전체를 처리한다). */
    static List<String> fields(SuggestionFieldsRequest request) {
        return request == null || request.fields() == null ? List.of() : request.fields();
    }
}
