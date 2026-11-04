package com.hiremate.posting;

import com.hiremate.company.CanvaConnectionService.CanvaDesign;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.List;

/** AI가 제안한 최대 두 디자인. 저장과 게시는 담당자가 별도로 실행한다. */
public record PosterProposal(@NotBlank @Size(max = 500) String reply,
        @NotNull @Size(max = 2) List<@Valid Recommendation> recommendations,
        @Size(max = 3) List<@Valid FreeTemplate> templates,
        @Schema(nullable = true) @Size(max = 80) String selectedTemplateId,
        @Schema(nullable = true) @Size(max = 100) String canvaQuery,
        @Size(max = 6) List<CanvaDesign> canvaDesigns,
        @Schema(nullable = true) @Size(max = 100) String externalQuery) {

    public PosterProposal {
        templates = templates == null ? List.of() : List.copyOf(templates);
        canvaDesigns = canvaDesigns == null ? List.of() : List.copyOf(canvaDesigns);
    }

    public PosterProposal(String reply, List<Recommendation> recommendations, List<FreeTemplate> templates,
            String selectedTemplateId, String canvaQuery, List<CanvaDesign> canvaDesigns) {
        this(reply, recommendations, templates, selectedTemplateId, canvaQuery, canvaDesigns, null);
    }

    public PosterProposal(String reply, List<Recommendation> recommendations, List<FreeTemplate> templates,
            String selectedTemplateId) {
        this(reply, recommendations, templates, selectedTemplateId, null, List.of());
    }

    public PosterProposal(String reply, List<Recommendation> recommendations) {
        this(reply, recommendations, List.of(), null);
    }

    public PosterProposal(String reply, List<Recommendation> recommendations, List<FreeTemplate> templates) {
        this(reply, recommendations, templates, null);
    }

    public record FreeTemplate(@NotBlank @Size(max = 80) String id,
            @NotBlank @Size(max = 100) String name,
            @NotBlank @Size(max = 500) String sourceUrl,
            @NotBlank @Size(max = 80) String license,
            @NotBlank @Size(max = 100000) String svg,
            @Schema(nullable = true) @Size(max = 2000) String thumbnailUrl) {
        public FreeTemplate(String id, String name, String sourceUrl, String license, String svg) {
            this(id, name, sourceUrl, license, svg, null);
        }
    }

    public record Recommendation(@NotNull @Valid PosterDesign design,
            @NotBlank @Size(max = 250) String reason) {
    }
}
