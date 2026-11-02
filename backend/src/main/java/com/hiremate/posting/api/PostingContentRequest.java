package com.hiremate.posting.api;

import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingRole;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

/**
 * 모집 조건(headcount부터)의 길이는 job_postings 테이블과 같다. 채용 인원은 정하지 않았으면 null이다.
 * 모집 조건을 빼고 보내면 빈 칸으로 저장한다. 고용 형태는 정규직 · 계약직 · 인턴 · 파견직 중 하나이고, 정하지 않았으면 빈 칸이다.
 */
public record PostingContentRequest(
        @NotBlank @Size(max = 200) String title,
        @NotNull @Size(max = 100) String jobCategory,
        @NotNull @Pattern(regexp = EMPLOYMENT_TYPES) String employmentType,
        @NotNull @Size(max = 50) String career,
        @NotNull @Size(max = 100) String location,
        @NotNull @Size(max = 5000) String intro,
        @NotNull @Size(max = 30) List<@NotNull @Size(max = 300) String> duties,
        @NotNull @Size(max = 30) List<@NotNull @Size(max = 300) String> qualifications,
        @NotNull @Size(max = 30) List<@NotNull @Size(max = 300) String> preferred,
        @NotNull @Size(max = 30) List<@NotNull @Size(max = 100) String> benefits,
        @Schema(nullable = true) @Min(1) @Max(9999) Integer headcount,
        @Schema(nullable = true) @Size(max = 50) String position,
        @Schema(nullable = true) @Size(max = 50) String education,
        @Schema(nullable = true) @Size(max = 100) String workHours,
        @Schema(nullable = true) @Size(max = 100) String salary,
        @Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED)
        @Size(max = 10) List<@NotNull @Valid PostingRole> roles) {

    /** 고를 수 있는 고용 형태. frontend EMPLOYMENT_TYPES, ai reviser와 같다. */
    static final String EMPLOYMENT_TYPES = "^(|정규직|계약직|인턴|파견직)$";

    PostingContent toContent() {
        return new PostingContent(title.trim(), jobCategory.trim(), employmentType.trim(), career.trim(),
                location.trim(), intro, clean(duties), clean(qualifications), clean(preferred), clean(benefits),
                headcount, trim(position), trim(education), trim(workHours), trim(salary), roles);
    }

    private static String trim(String value) {
        return value == null ? "" : value.trim();
    }

    private static List<String> clean(List<String> lines) {
        return lines.stream().map(String::trim).filter(line -> !line.isEmpty()).toList();
    }
}
