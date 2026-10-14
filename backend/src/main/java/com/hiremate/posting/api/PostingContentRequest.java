package com.hiremate.posting.api;

import com.hiremate.posting.PostingContent;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

public record PostingContentRequest(
        @NotBlank @Size(max = 200) String title,
        @NotNull @Size(max = 100) String jobCategory,
        @NotNull @Size(max = 50) String employmentType,
        @NotNull @Size(max = 50) String career,
        @NotNull @Size(max = 100) String location,
        @NotNull @Size(max = 5000) String intro,
        @NotNull @Size(max = 30) List<@NotNull @Size(max = 300) String> duties,
        @NotNull @Size(max = 30) List<@NotNull @Size(max = 300) String> qualifications,
        @NotNull @Size(max = 30) List<@NotNull @Size(max = 300) String> preferred,
        @NotNull @Size(max = 30) List<@NotNull @Size(max = 100) String> benefits) {

    PostingContent toContent() {
        return new PostingContent(title.trim(), jobCategory.trim(), employmentType.trim(), career.trim(),
                location.trim(), intro, clean(duties), clean(qualifications), clean(preferred), clean(benefits));
    }

    private static List<String> clean(List<String> lines) {
        return lines.stream().map(String::trim).filter(line -> !line.isEmpty()).toList();
    }
}
