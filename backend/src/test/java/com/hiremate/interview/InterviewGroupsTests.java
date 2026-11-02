package com.hiremate.interview;

import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.interview.domain.InterviewSession;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class InterviewGroupsTests {

    @Test
    @DisplayName("같은 시간 면접자는 UUID 부호에 관계없이 화면의 지원서 ID 문자열 순서로 정렬한다")
    void ordersMembersAcrossUuidSignBoundary() {
        UUID first = UUID.fromString("7fffffff-0000-0000-0000-000000000001");
        UUID second = UUID.fromString("80000000-0000-0000-0000-000000000001");
        UUID company = new UUID(0, 1);
        UUID stage = new UUID(0, 2);
        UUID hr = new UUID(0, 3);
        UUID practical = new UUID(0, 4);
        Instant at = Instant.parse("2026-11-03T00:00:00Z");
        var groups = InterviewGroups.byApplication(List.of(
                new InterviewSession(company, stage, second, hr, practical),
                new InterviewSession(company, stage, first, hr, practical)), Map.of(first, at, second, at));
        assertThat(groups.get(first)).extracting(InterviewSession::getApplicationId).containsExactly(first, second);
        assertThat(groups.get(second)).extracting(InterviewSession::getApplicationId).containsExactly(first, second);
    }
}
