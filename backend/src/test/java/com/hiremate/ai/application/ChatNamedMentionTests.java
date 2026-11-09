package com.hiremate.ai.application;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.apply.AnalysisStatus;
import com.hiremate.screening.CandidateRow;
import com.hiremate.screening.Decision;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

/** @ 없이 이름만 쓴 지원자도 멘션처럼 넘긴다. */
class ChatNamedMentionTests {

    private final UUID shin = UUID.randomUUID();
    private final UUID kimMinsu = UUID.randomUUID();
    private final UUID kimMin = UUID.randomUUID();
    private final UUID lee1 = UUID.randomUUID();
    private final UUID lee2 = UUID.randomUUID();
    private final List<CandidateRow> rows = List.of(row(shin, "신예준"), row(kimMinsu, "김민수"), row(kimMin, "김민"),
            row(lee1, "이서연"), row(lee2, "이서연"));

    @Test
    void addsNamedApplicantsAfterMentionsInMessageOrder() {
        assertThat(ChatService.withNamed("김민수랑 신예준 비교해줘", List.of(lee1), rows))
                .containsExactly(lee1, kimMinsu, shin);
    }

    @Test
    void keepsMentionsWithoutDuplicates() {
        assertThat(ChatService.withNamed("신예준 단점 알려줘", List.of(shin), rows)).containsExactly(shin);
    }

    @Test
    void skipsShorterNameInsideLongerOneUnlessUsedAlone() {
        assertThat(ChatService.withNamed("김민수 장점", List.of(), rows)).containsExactly(kimMinsu);
        assertThat(ChatService.withNamed("김민수와 김민 비교", List.of(), rows)).containsExactly(kimMinsu, kimMin);
    }

    @Test
    void skipsHomonymsAndUnknownNames() {
        assertThat(ChatService.withNamed("이서연 경력 알려줘", List.of(), rows)).isEmpty();
        assertThat(ChatService.withNamed("금융 경험 찾아줘", List.of(), rows)).isEmpty();
    }

    private static CandidateRow row(UUID id, String name) {
        return new CandidateRow(id, name, 3, null, Decision.PENDING, false, false, false, null,
                AnalysisStatus.DONE, List.of(), 0, 0, 0, 0, List.of());
    }
}
