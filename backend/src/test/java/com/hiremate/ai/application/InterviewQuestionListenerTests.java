package com.hiremate.ai.application;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.hiremate.interview.InterviewService;
import com.hiremate.recruit.RecruitService;
import com.hiremate.recruit.RecruitmentInfo;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageConfirmed;
import com.hiremate.recruit.StageInfo;
import com.hiremate.recruit.StageStatus;
import com.hiremate.recruit.StageType;
import com.hiremate.screening.ScreeningService;
import com.hiremate.screening.StageResults;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.context.ApplicationEventPublisher;

class InterviewQuestionListenerTests {

    @Test
    @DisplayName("모든 합격자의 준비 상태와 개별 이벤트를 먼저 기록하고 자료 분석은 기다리지 않는다")
    void schedulesApplicantsIndependently() {
        RecruitService recruits = mock(RecruitService.class);
        ScreeningService screening = mock(ScreeningService.class);
        InterviewAiService interviews = mock(InterviewAiService.class);
        InterviewService records = mock(InterviewService.class);
        ApplicationEventPublisher events = mock(ApplicationEventPublisher.class);
        var listener = new InterviewQuestionListener(recruits, screening, interviews, records, events);
        UUID company = UUID.randomUUID();
        UUID recruitment = UUID.randomUUID();
        UUID document = UUID.randomUUID();
        UUID interview = UUID.randomUUID();
        UUID first = UUID.randomUUID();
        UUID second = UUID.randomUUID();
        when(recruits.getByStage(company, document)).thenReturn(new RecruitmentInfo(recruitment, company,
                "채용", RecruitmentStatus.IN_PROGRESS, document, List.of(
                        new StageInfo(document, recruitment, 1, "서류", StageType.DOCUMENT, StageStatus.CONFIRMED,
                                null, null, null, null),
                        new StageInfo(interview, recruitment, 2, "면접", StageType.INTERVIEW, StageStatus.PENDING,
                                null, null, null, null)), null, null, null));
        when(screening.results(company, document)).thenReturn(
                new StageResults(document, List.of(first, second), List.of(), 0));

        listener.on(new StageConfirmed(document, company));

        verify(records).startPreparing(company, interview, first);
        verify(records).startPreparing(company, interview, second);
        verify(events).publishEvent(new InterviewQuestionsRequested(company, interview, first));
        verify(events).publishEvent(new InterviewQuestionsRequested(company, interview, second));
        verifyNoInteractions(interviews);
    }
}
