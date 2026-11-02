package com.hiremate.interview;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executors;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

class InterviewSharedNoteTests extends IntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Test
    @DisplayName("공유 기록은 작성자만 수정하고 HR과 배정 면접관이 읽으며 개인 메모는 포함하지 않는다")
    void sharedNotesDoNotExposePrivateMemos() throws Exception {
        Room room = room();
        expect(room.people().put(room.root() + "/memo", body("PRIVATE-HR", 0)), 200);
        expect(room.people().put(room.notes() + "/me", body("협업 사실", 0)), 200);
        expect(room.practical().put(room.notes() + "/me", body("직무 확인 사실", 0)), 200);
        String hr = expect(room.interview().hr().get(room.hrNotes()), 200).body();
        assertThat(hr).contains("협업 사실", "직무 확인 사실", "HR", "PRACTICAL").doesNotContain("PRIVATE-HR");
        assertThat(json(expect(room.practical().get(room.notes()), 200))).hasSize(2);
        expect(room.interview().hr().put(room.notes() + "/me", body("우회", 0)), 403);
        expect(newInterviewer(room.interview().hr(), "미배정").get(room.notes()), 403);
        expect(newHr().get(room.hrNotes()), 404);
        expect(room.people().put(room.notes() + "/me", body("오래된 초안", 0)), 409);
        assertThat(expect(room.interview().hr().get(room.hrNotes()), 200).body()).contains("협업 사실");
        expect(room.people().post(room.root() + "/end", null), 200);
        expect(room.people().put(room.notes() + "/me", body("종료 후", 1)), 409);
    }

    @Test
    @DisplayName("인사와 실무 동시 저장은 성공하고 같은 작성자의 동일 버전 저장은 한 건만 성공한다")
    void concurrentWritesAreScopedToAuthor() throws Exception {
        Room room = room();
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            var people = executor.submit(() -> room.people().put(room.notes() + "/me", body("인사", 0)).statusCode());
            var practical = executor.submit(() ->
                    room.practical().put(room.notes() + "/me", body("실무", 0)).statusCode());
            assertThat(List.of(people.get(), practical.get())).containsOnly(200);
            var first = executor.submit(() -> room.people().put(room.notes() + "/me", body("초안1", 1)).statusCode());
            var second = executor.submit(() -> room.people().put(room.notes() + "/me", body("초안2", 1)).statusCode());
            assertThat(List.of(first.get(), second.get())).containsExactlyInAnyOrder(200, 409);
        }
    }

    private Room room() throws Exception {
        Interview interview = interviewStage();
        TestApi people = newInterviewer(interview.hr(), "가상 인사");
        TestApi practical = newInterviewer(interview.hr(), "가상 실무");
        expect(interview.hr().put(interview.stage() + "/interview/assignment",
                Map.of("hrMemberId", people.memberId(), "practicalMemberId", practical.memberId())), 200);
        jdbc.update("UPDATE interview_sessions SET status = 'IN_PROGRESS' WHERE stage_id = ? AND application_id = ?",
                interview.stageId(), interview.applicationId());
        return new Room(interview, people, practical);
    }

    private static Map<String, Object> body(String text, long version) {
        return Map.of("text", text, "expectedVersion", version);
    }

    private record Room(Interview interview, TestApi people, TestApi practical) {
        String root() {
            return "/api/interviewer/sessions/" + interview.stageId() + "/" + interview.applicationId();
        }

        String notes() {
            return root() + "/shared-notes";
        }

        String hrNotes() {
            return interview.candidate() + "/interview/shared-notes";
        }
    }
}
