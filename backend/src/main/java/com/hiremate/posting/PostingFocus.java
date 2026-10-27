package com.hiremate.posting;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import java.util.List;

/**
 * AI 수정 요청에서 HR이 공고 편집 화면에서 고른 줄. Posting Agent는 이 줄만 고친다.
 *
 * @param field 고른 본문 칸(PostingContent의 JSON 이름). 회사 소개는 칸 전체를, 나머지는 목록의 줄 하나를 고른다
 * @param index 목록 칸의 몇 번째 줄인지(0부터). 회사 소개를 고르면 null이다
 */
public record PostingFocus(
        @NotNull @Pattern(regexp = "intro|duties|qualifications|preferred|benefits") String field,
        @Schema(nullable = true) @PositiveOrZero Integer index) {

    /** 고른 줄이 저장된 공고에 있는지. 빈 줄은 저장할 때 빠지므로 고를 수 없다. */
    public boolean isIn(PostingContent content) {
        if ("intro".equals(field)) {
            return index == null;
        }
        return index != null && index >= 0 && index < lines(content).size();
    }

    /** 고른 목록 칸의 줄. 회사 소개를 골랐으면 빈 목록이다. */
    public List<String> lines(PostingContent content) {
        return switch (field) {
            case "duties" -> content.duties();
            case "qualifications" -> content.qualifications();
            case "preferred" -> content.preferred();
            case "benefits" -> content.benefits();
            default -> List.of();
        };
    }
}
