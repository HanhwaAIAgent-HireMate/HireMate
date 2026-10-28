package com.hiremate.posting;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** AI가 제안한 최대 두 디자인. 저장과 게시는 담당자가 별도로 실행한다. */
public record PosterProposal(@NotBlank @Size(max = 500) String reply,
        @NotNull @Size(max = 2) List<@Valid Recommendation> recommendations) {

    public record Recommendation(@NotNull @Valid PosterDesign design,
            @NotBlank @Size(max = 250) String reason) {
    }
}
