package com.hiremate.ai.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.hiremate.ai.application.PosterAgent;
import com.hiremate.company.CanvaConnectionService;
import com.hiremate.company.CompanyService;
import com.hiremate.company.PosterBrand;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.posting.OrshotLibrary;
import com.hiremate.posting.PosterDesign;
import com.hiremate.posting.PosterProposal;
import com.hiremate.posting.PosterTemplateSearch;
import com.hiremate.posting.PostingService;
import com.hiremate.posting.PostingView;
import com.hiremate.posting.TemplatedLibrary;
import com.hiremate.recruit.RecruitmentStatus;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Validator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.params.provider.ValueSource;

class PosterAiControllerTests {
    @ParameterizedTest
    @EnumSource(PosterProposal.CandidateMode.class)
    @DisplayName("정적 후보 중 하나를 새 Templated 양식으로 등록하고 모션은 Orshot 후보를 준비한다")
    void keepsCandidateSourcesForEachRequest(PosterProposal.CandidateMode mode) {
        PostingService postings = mock(PostingService.class);
        CompanyService companies = mock(CompanyService.class);
        PosterAgent agent = mock(PosterAgent.class);
        Validator validator = mock(Validator.class);
        CanvaConnectionService canva = mock(CanvaConnectionService.class);
        TemplatedLibrary templated = mock(TemplatedLibrary.class);
        OrshotLibrary orshot = mock(OrshotLibrary.class);
        AuthenticatedMember member = mock(AuthenticatedMember.class);
        HttpSession session = mock(HttpSession.class);
        UUID recruitment = UUID.randomUUID();
        UUID company = UUID.randomUUID();
        when(member.companyId()).thenReturn(company);
        PostingView posting = mock(PostingView.class);
        when(posting.status()).thenReturn(RecruitmentStatus.DRAFT);
        when(posting.stages()).thenReturn(List.of());
        when(postings.view(company, recruitment)).thenReturn(posting);
        when(companies.posterBrand(company)).thenReturn(PosterBrand.DEFAULT);
        when(canva.status(member, session)).thenReturn(
                new CanvaConnectionService.CanvaStatus(false, false, null, List.of()));
        PosterProposal search = new PosterProposal("후보 준비", List.of(), List.of(),
                null, null, List.of(), "banking recruitment", mode);
        when(agent.design(any(), anyString())).thenReturn(search);
        PosterDesign design = new PosterDesign(PosterDesign.Template.CLASSIC, PosterDesign.Mood.TRUST,
                "#082858", 1, true, false, null, PosterDesign.BackgroundStyle.SOLID,
                Map.of(), List.of(), "{\"source\":{\"id\":\"generated:new-design\"}}", null, PosterDesign.Motion.NONE);
        when(agent.generate(any(), anyString())).thenReturn(new PosterProposal("새 디자인",
                List.of(new PosterProposal.Recommendation(design, "새 구성"),
                        new PosterProposal.Recommendation(design, "다른 구성"))));
        var first = new PosterProposal.FreeTemplate("orshot:one", "Orshot 1",
                "https://orshot.com/templates/", "Orshot 계정 디자인", "<svg/>");
        var second = new PosterProposal.FreeTemplate("orshot:two", "Orshot 2",
                "https://orshot.com/templates/", "Orshot 계정 디자인", "<svg/>");
        when(orshot.search(anyString(), any(), any())).thenReturn(List.of(first, second));
        PosterAiController controller = new PosterAiController(postings, companies, agent, validator, canva,
                templated, mock(PosterTemplateSearch.class), orshot);
        List<String> progress = new java.util.ArrayList<>();
        PosterProposal result = controller.designWithProgress(member, recruitment,
                new PosterAiController.PosterAiRequest("직무에 어울리는 공고 찾아줘", design, List.of(), List.of()),
                session, progress::add);
        assertThat(progress).containsExactly("공고와 기업 정보를 확인하고 있어요",
                "요청에 맞는 포스터 디자인을 구상하고 있어요", "템플릿 후보를 조회하고 새 디자인을 준비하고 있어요");
        switch (mode) {
            case INITIAL -> {
                assertThat(result.templates()).extracting(PosterProposal.FreeTemplate::id)
                        .containsExactly("orshot:one");
                assertThat(result.recommendations()).hasSize(2);
                assertThat(result.recommendations().getFirst().design().canvasJson())
                        .contains("\"templatedRegistration\":true");
                assertThat(result.recommendations().get(1).design().canvasJson())
                        .doesNotContain("templatedRegistration");
            }
            case STATIC -> {
                assertThat(result.templates()).extracting(PosterProposal.FreeTemplate::id)
                        .containsExactly("orshot:one");
                assertThat(result.recommendations()).hasSize(1);
            }
            case MOTION -> {
                assertThat(result.templates()).extracting(PosterProposal.FreeTemplate::id)
                        .containsExactly("orshot:one", "orshot:two");
                assertThat(result.recommendations()).isEmpty();
            }
            default -> throw new IllegalStateException("Unknown candidate mode");
        }
    }

    @ParameterizedTest
    @ValueSource(booleans = {false, true})
    @DisplayName("외부 후보가 없으면 새 디자인을 만들고 디자인 검증에서 움직임을 보존한다")
    void returnsSecuredRecommendation(boolean externalSearch) {
        PostingService postings = mock(PostingService.class);
        CompanyService companies = mock(CompanyService.class);
        PosterAgent agent = mock(PosterAgent.class);
        Validator validator = mock(Validator.class);
        CanvaConnectionService canva = mock(CanvaConnectionService.class);
        AuthenticatedMember member = mock(AuthenticatedMember.class);
        HttpSession session = mock(HttpSession.class);
        UUID recruitment = UUID.randomUUID();
        UUID company = UUID.randomUUID();
        when(member.companyId()).thenReturn(company);
        PostingView posting = mock(PostingView.class);
        when(posting.status()).thenReturn(RecruitmentStatus.DRAFT);
        when(posting.stages()).thenReturn(List.of());
        when(postings.view(company, recruitment)).thenReturn(posting);
        when(companies.posterBrand(company)).thenReturn(PosterBrand.DEFAULT);
        when(canva.status(member, session)).thenReturn(
                new CanvaConnectionService.CanvaStatus(false, false, null, List.of()));
        String canvas = externalSearch ? "{\"source\":{\"id\":\"generated:new-design\"}}" : null;
        PosterDesign design = new PosterDesign(PosterDesign.Template.CLASSIC, PosterDesign.Mood.TRUST,
                "#082858", 1, true, false, null, PosterDesign.BackgroundStyle.SOLID,
                Map.of(), List.of(), canvas, "금융의 다음을 함께 만듭니다", PosterDesign.Motion.WAVE);
        PosterProposal proposal = new PosterProposal("상단 움직임 수정안",
                List.of(new PosterProposal.Recommendation(design, "상단 장식만 변경")));
        if (externalSearch) {
            PosterProposal search = new PosterProposal("외부 템플릿 검색", List.of(), List.of(),
                    null, null, List.of(), "banking recruitment");
            when(agent.design(any(), anyString())).thenReturn(search);
            when(agent.generate(any(), anyString())).thenReturn(proposal);
            when(validator.validate(search)).thenReturn(Set.of());
        } else {
            when(agent.design(any(), anyString())).thenReturn(proposal);
        }
        when(validator.validate(proposal)).thenReturn(Set.of());
        PosterTemplateSearch templateSearch = mock(PosterTemplateSearch.class);
        when(templateSearch.combine(any(), any(), any()))
                .thenReturn(new PosterTemplateSearch.Result(List.of(), List.of()));
        PosterAiController controller = new PosterAiController(postings, companies, agent, validator, canva,
                mock(TemplatedLibrary.class), templateSearch, mock(OrshotLibrary.class));
        PosterProposal result = controller.design(member, recruitment,
                new PosterAiController.PosterAiRequest("상단 물결을 움직이게", design, List.of(), List.of()), session);
        assertThat(result.recommendations().getFirst().design()).isEqualTo(design);
        if (externalSearch) {
            assertThat(result.reply()).contains("HireMate에서 새 디자인 1개");
        }
    }
}
