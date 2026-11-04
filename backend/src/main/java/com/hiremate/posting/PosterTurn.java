package com.hiremate.posting;

import com.hiremate.posting.PosterProposal.FreeTemplate;
import com.hiremate.posting.PosterProposal.Recommendation;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** 현재 편집 세션의 디자인 대화. 업무 실행이나 회사 사실의 근거로 쓰지 않는다. */
public record PosterTurn(@NotNull Role role, @NotBlank @Size(max = 1000) String text,
        @Valid @Schema(nullable = true) PosterDesign design,
        @NotNull @Size(max = 2) List<@NotNull @Valid Recommendation> recommendations,
        @Size(max = 3) List<@NotNull @Valid FreeTemplate> templates) {
    public PosterTurn {
        templates = templates == null ? List.of() : List.copyOf(templates);
    }

    public PosterTurn(Role role, String text, PosterDesign design, List<Recommendation> recommendations) {
        this(role, text, design, recommendations, List.of());
    }

    public enum Role {
        USER, ASSISTANT
    }
}
