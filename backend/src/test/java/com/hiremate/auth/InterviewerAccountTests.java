package com.hiremate.auth;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

/** HR이 기업 설정에서 면접관 계정을 만들고, 그 계정으로 로그인한다. */
class InterviewerAccountTests extends IntegrationTest {

    private static final String PATH = "/api/companies/me/interviewers";

    @Test
    @DisplayName("HR이 만든 면접관 계정은 같은 기업의 면접관으로 로그인하고, 계정 목록은 HR만 본다")
    void createsInterviewerAccountsThatCanLogIn() throws Exception {
        TestApi hr = newHr();
        String email = "kim-" + UUID.randomUUID() + "@example.com";

        JsonNode created = json(expect(hr.post(PATH,
                Map.of("name", "김지민", "email", email, "password", INTERVIEWER_PASSWORD)), 201));
        assertThat(created.path("name").asString()).isEqualTo("김지민");
        assertThat(created.path("email").asString()).isEqualTo(email);

        JsonNode list = json(expect(hr.get(PATH), 200));
        assertThat(list).hasSize(1);
        assertThat(list.get(0).path("memberId").asString()).isEqualTo(created.path("memberId").asString());

        assertThat(json(expect(hr.post(PATH, Map.of("name", "중복", "email", email.toUpperCase(),
                "password", INTERVIEWER_PASSWORD)), 409)).path("code").asString())
                .isEqualTo("EMAIL_ALREADY_EXISTS");
        expect(hr.post(PATH, Map.of("name", "짧은 비밀번호", "email", "short-" + UUID.randomUUID() + "@example.com",
                "password", "short-pass1")), 400);

        TestApi interviewer = anonymous();
        interviewer.login(email, INTERVIEWER_PASSWORD);
        JsonNode me = json(expect(interviewer.get("/api/auth/me"), 200));
        assertThat(me.path("role").asString()).isEqualTo("INTERVIEWER");
        assertThat(me.path("companyId").asString()).isEqualTo(hr.companyId().toString());
        assertThat(json(expect(interviewer.get(PATH), 403)).path("code").asString()).isEqualTo("FORBIDDEN");
    }

    @Test
    @DisplayName("다른 기업의 면접관 계정은 목록에 보이지 않는다")
    void listsOnlyOwnCompanyInterviewers() throws Exception {
        TestApi first = newHr();
        TestApi second = newHr();
        newInterviewer(first, "김지민");

        assertThat(json(expect(second.get(PATH), 200))).isEmpty();
        assertThat(json(expect(first.get(PATH), 200))).hasSize(1);
    }
}
