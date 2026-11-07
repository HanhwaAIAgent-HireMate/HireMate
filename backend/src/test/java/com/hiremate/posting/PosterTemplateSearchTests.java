package com.hiremate.posting;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.company.CanvaConnectionService.CanvaDesign;
import java.util.List;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

class PosterTemplateSearchTests {
    @Test
    void excludesAppliedOriginsAcrossProvidersAndKeepsNewCandidates() {
        var search = new PosterTemplateSearch(WebClient.builder());
        var result = search.combine(List.of(template("templated:one"), template("orshot:12"), template("orshot:13")),
                List.of(new CanvaDesign("D12345", "이미 적용", "", ""), new CanvaDesign("D67890", "새 디자인", "", "")),
                Set.of("templated:one", "orshot:12", "canva:D12345"));
        assertThat(result.templates()).extracting(PosterProposal.FreeTemplate::id).containsExactly("orshot:13");
        assertThat(result.designs()).extracting(CanvaDesign::id).containsExactly("D67890");
    }

    private static PosterProposal.FreeTemplate template(String id) {
        return new PosterProposal.FreeTemplate(id, id, "https://orshot.com/templates/", "계정 디자인", "<svg/>", "");
    }
}
