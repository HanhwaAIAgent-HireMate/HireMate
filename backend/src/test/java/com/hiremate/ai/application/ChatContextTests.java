package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationService;
import com.hiremate.assessment.AssessmentResultView;
import com.hiremate.assessment.AssessmentService;
import com.hiremate.company.CompanyProfile;
import com.hiremate.company.CompanyService;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.CandidatePage;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.CandidateSort;
import com.hiremate.screening.Decision;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageTabService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.UUID;
import java.util.stream.IntStream;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class ChatContextTests {

    @Test
    @DisplayName("전형의 지원자가 200명을 넘어도 마지막 선택 지원자까지 AI에 넘긴다")
    void preparesEveryCandidateAcrossPages() {
        UUID companyId = UUID.randomUUID();
        UUID recruitmentId = UUID.randomUUID();
        UUID stageId = UUID.randomUUID();
        List<CandidateRow> candidates = IntStream.rangeClosed(1, 201)
                .mapToObj(number -> new CandidateRow(UUID.randomUUID(), "지원자" + number,
                        number == 201 ? 40 : 1, "개발기업", Decision.PENDING, number == 201,
                        false, true, null, AnalysisStatus.DONE, false, List.of(), null, null, null, 0, null, 0))
                .toList();
        ScreeningService screening = mock(ScreeningService.class);
        when(screening.candidates(eq(companyId), eq(stageId), any(), isNull(), eq(CandidateSort.QUALIFICATION),
                eq(0), anyInt())).thenReturn(new CandidatePage(201, candidates.subList(0, 200)));
        when(screening.candidates(eq(companyId), eq(stageId), any(), isNull(), eq(CandidateSort.QUALIFICATION),
                eq(1), anyInt())).thenReturn(new CandidatePage(201, candidates.subList(200, 201)));
        StageInfo stage = new StageInfo(stageId, recruitmentId, 1, "서류 전형", StageType.DOCUMENT,
                StageStatus.ACTIVE, null, null, null, null);
        RecruitService recruits = mock(RecruitService.class);
        when(recruits.getByStage(companyId, stageId)).thenReturn(new RecruitmentInfo(recruitmentId, companyId,
                "개발자 채용", RecruitmentStatus.IN_PROGRESS, stageId, List.of(stage), Instant.EPOCH, null, null));
        CompanyService companies = mock(CompanyService.class);
        when(companies.profile(companyId)).thenReturn(new CompanyProfile(companyId, "개발기업", "소개", "문화",
                List.of(), List.of()));
        PostingService postings = mock(PostingService.class);
        PostingContent content = new PostingContent("개발자 채용", "백엔드 개발", "정규직", "경력", "서울", "소개",
                List.of(), List.of(), List.of(), List.of());
        when(postings.draftContext(companyId, recruitmentId)).thenReturn(new PostingDraftContext(recruitmentId,
                RecruitmentStatus.IN_PROGRESS, content, List.of(), Set.of()));
        ChatService chat = new ChatService(screening, recruits, mock(ApplicationService.class), companies,
                postings, mock(RootAgent.class), mock(InterviewAiService.class), mock(AiSettings.class),
                mock(AssessmentService.class), mock(StageTabService.class));

        ChatInput input = chat.prepare(companyId, stageId, UUID.randomUUID(), null,
                "선택 지원자 중 경력이 가장 긴 사람은?", List.of(), List.of());

        assertThat(input.candidates()).hasSize(201);
        assertThat(input.context().candidates()).containsExactlyElementsOf(candidates);
        assertThat(input.context().candidates().getLast().selected()).isTrue();
        assertThat(input.context().candidates().getLast().careerYears()).isEqualTo(40);
    }

    @Test
    @DisplayName("평가 전형이면 지원자별 영역 점수 · 등급을 AI에 넘기고, 빈 NCS 영역은 null로 둔다")
    void preparesAssessmentAreasAndGrade() {
        UUID companyId = UUID.randomUUID();
        UUID recruitmentId = UUID.randomUUID();
        UUID stageId = UUID.randomUUID();
        CandidateRow scored = new CandidateRow(UUID.randomUUID(), "김도현", 8, "누리페이", Decision.PENDING, false,
                false, true, new BigDecimal("93.8"), AnalysisStatus.DONE, false, List.of(), null, null, null, 0, null,
                0);
        CandidateRow empty = new CandidateRow(UUID.randomUUID(), "나새롬", 3, "개발기업", Decision.PENDING, false,
                false, true, null, AnalysisStatus.DONE, false, List.of(), null, null, null, 0, null, 0);
        ScreeningService screening = mock(ScreeningService.class);
        when(screening.candidates(eq(companyId), eq(stageId), any(), isNull(), eq(CandidateSort.QUALIFICATION),
                eq(0), anyInt())).thenReturn(new CandidatePage(2, List.of(scored, empty)));
        StageInfo stage = new StageInfo(stageId, recruitmentId, 2, "직무역량 평가", StageType.ASSESSMENT,
                StageStatus.ACTIVE, null, null, null, null);
        RecruitService recruits = mock(RecruitService.class);
        when(recruits.getByStage(companyId, stageId)).thenReturn(new RecruitmentInfo(recruitmentId, companyId,
                "개발자 채용", RecruitmentStatus.IN_PROGRESS, stageId, List.of(stage), Instant.EPOCH, null, null));
        CompanyService companies = mock(CompanyService.class);
        when(companies.profile(companyId)).thenReturn(new CompanyProfile(companyId, "개발기업", "소개", "문화",
                List.of(), List.of()));
        PostingService postings = mock(PostingService.class);
        PostingContent content = new PostingContent("개발자 채용", "백엔드 개발", "정규직", "경력", "서울", "소개",
                List.of(), List.of(), List.of(), List.of());
        when(postings.draftContext(companyId, recruitmentId)).thenReturn(new PostingDraftContext(recruitmentId,
                RecruitmentStatus.IN_PROGRESS, content, List.of(), Set.of()));
        Map<String, BigDecimal> areas = new HashMap<>();
        areas.put("의사소통능력", new BigDecimal("94"));
        areas.put("수리능력", new BigDecimal("91"));
        AssessmentService assessments = mock(AssessmentService.class);
        when(assessments.find(companyId, stageId, scored.applicationId())).thenReturn(Optional.of(
                new AssessmentResultView(scored.applicationId(), new BigDecimal("93.8"), areas, "A", null, null, null,
                        null, "TABLE", Instant.EPOCH)));
        when(assessments.find(companyId, stageId, empty.applicationId())).thenReturn(Optional.empty());
        ChatService chat = new ChatService(screening, recruits, mock(ApplicationService.class), companies,
                postings, mock(RootAgent.class), mock(InterviewAiService.class), mock(AiSettings.class), assessments,
                mock(StageTabService.class));

        ChatInput input = chat.prepare(companyId, stageId, UUID.randomUUID(), null,
                "의사소통능력 90점 이상인 사람만 옮겨줘", List.of(), List.of());

        Map<UUID, ChatContext.Assessment> sent = input.context().assessments();
        assertThat(sent).containsOnlyKeys(scored.applicationId());
        ChatContext.Assessment result = sent.get(scored.applicationId());
        assertThat(result.grade()).isEqualTo("A");
        assertThat(result.areas()).containsKeys("의사소통능력", "수리능력", "문제해결능력", "정보능력", "기술능력");
        assertThat(result.areas().get("의사소통능력")).isEqualByComparingTo("94");
        assertThat(result.areas().get("문제해결능력")).isNull();
    }
}
