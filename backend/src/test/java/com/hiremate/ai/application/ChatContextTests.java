package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.apply.ApplicationService;
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
import java.time.Instant;
import java.util.List;
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
        when(screening.candidates(eq(companyId), eq(stageId), isNull(), eq(CandidateSort.QUALIFICATION),
                eq(0), anyInt())).thenReturn(new CandidatePage(201, candidates.subList(0, 200)));
        when(screening.candidates(eq(companyId), eq(stageId), isNull(), eq(CandidateSort.QUALIFICATION),
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
                postings, mock(RootAgent.class), mock(InterviewAiService.class), mock(AiSettings.class));

        ChatInput input = chat.prepare(companyId, stageId, UUID.randomUUID(), "선택 지원자 중 경력이 가장 긴 사람은?",
                List.of(), List.of());

        assertThat(input.candidates()).hasSize(201);
        assertThat(input.context().candidates()).containsExactlyElementsOf(candidates);
        assertThat(input.context().candidates().getLast().selected()).isTrue();
        assertThat(input.context().candidates().getLast().careerYears()).isEqualTo(40);
    }
}
