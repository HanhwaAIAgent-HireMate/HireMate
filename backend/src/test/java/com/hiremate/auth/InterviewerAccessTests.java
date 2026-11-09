package com.hiremate.auth;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.doReturn;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.apply.DemoApplicantPhotos;
import com.hiremate.file.application.FileStorage;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;
import tools.jackson.databind.JsonNode;

/** 면접관은 /api/interviewer와 배정된 지원자의 지원 자료 읽기 경로만 쓴다. 그 밖의 업무 API는 모두 403이다. */
class InterviewerAccessTests extends IntegrationTest {

    /** SecurityConfig의 면접관 경로와 같아야 한다. 새 API는 여기에 넣지 않으면 면접관에게 막힌다. */
    static final Set<String> INTERVIEWER_READS = Set.of(
            "GET /api/stages/{stageId}/candidates/{applicationId}",
            "GET /api/stages/{stageId}/candidates/{applicationId}/history",
            "GET /api/stages/{stageId}/candidates/{applicationId}/analysis",
            "GET /api/stages/{stageId}/candidates/{applicationId}/profile",
            "GET /api/recruitments/{recruitmentId}/applications/{applicationId}/documents/{type}",
            "GET /api/recruitments/{recruitmentId}/applications/{applicationId}/photo",
            "GET /api/stages/{stageId}/tabs",
            "POST /api/stages/{stageId}/tabs",
            "PATCH /api/stages/{stageId}/tabs/{tabId}",
            "DELETE /api/stages/{stageId}/tabs/{tabId}",
            "GET /api/stages/{stageId}/tabs/{tabId}/chat",
            "POST /api/stages/{stageId}/tabs/{tabId}/chat");

    @Autowired
    @Qualifier("requestMappingHandlerMapping")
    private RequestMappingHandlerMapping mappings;

    @Autowired
    private FileStorage storage;

    @MockitoSpyBean
    private DemoApplicantPhotos demoPhotos;

    @Test
    @DisplayName("배정된 면접관도 허용 목록 밖의 업무 API는 모두 403이다")
    void everyOtherRouteIsForbiddenForInterviewers() throws Exception {
        Interview interview = interviewStage();
        doReturn(true).when(demoPhotos).enabled(interview.recruitmentId());
        TestApi interviewer = assigned(interview);
        List<String> opened = new ArrayList<>();
        for (Map.Entry<RequestMappingInfo, ?> entry : mappings.getHandlerMethods().entrySet()) {
            RequestMappingInfo info = entry.getKey();
            for (String pattern : info.getPatternValues()) {
                if (!pattern.startsWith("/api/") || pattern.startsWith("/api/auth/")
                        || pattern.startsWith("/api/public/") || pattern.startsWith("/api/interviewer/")) {
                    continue;
                }
                Set<RequestMethod> methods = info.getMethodsCondition().getMethods();
                for (RequestMethod method : methods.isEmpty() ? Set.of(RequestMethod.GET) : methods) {
                    if (INTERVIEWER_READS.contains(method + " " + pattern)) {
                        continue;
                    }
                    HttpResponse<String> response = send(interviewer, method, path(pattern, interview));
                    if (response.statusCode() != 403) {
                        opened.add(method + " " + pattern + " → " + response.statusCode());
                    }
                }
            }
        }
        assertThat(opened).isEmpty();
    }

    @Test
    @DisplayName("지원 자료는 배정된 지원자만 열리고, 이번 전형의 합격 · 불합격 결정은 숨긴다")
    void readsOnlyAssignedCandidatesWithoutCurrentDecision() throws Exception {
        for (int i = 0; i < 8; i++) {
            storage.save("example-applicants/" + i + ".png", new byte[] {1, 2, 3});
        }
        Interview interview = interviewStage();
        doReturn(true).when(demoPhotos).enabled(interview.recruitmentId());
        TestApi interviewer = newInterviewer(interview.hr(), "김지민");
        String documents = "/api/recruitments/" + interview.recruitmentId() + "/applications/"
                + interview.applicationId() + "/documents/RESUME";
        String photo = "/api/recruitments/" + interview.recruitmentId() + "/applications/"
                + interview.applicationId() + "/photo";
        expect(interviewer.get(interview.candidate()), 403);
        expect(interviewer.get(documents), 403);
        expect(interviewer.get(photo), 403);

        assign(interview, interviewer);
        expect(interview.hr().post(interview.stage() + "/decisions", Map.of("applicationIds",
                List.of(interview.applicationId().toString()), "decision", "PASS")), 204);
        assertThat(json(expect(interviewer.get(interview.candidate()), 200)).path("row").path("decision")
                .asString()).isEqualTo("PENDING");
        JsonNode history = json(expect(interviewer.get(interview.candidate() + "/history"), 200));
        JsonNode current = history.get(history.size() - 1);
        assertThat(current.path("decision").asString()).isEqualTo("PENDING");
        assertThat(current.path("finalResult").isNull()).isTrue();
        expect(interviewer.get(documents), 200);
        assertThat(interviewer.getBytes(photo).statusCode()).isEqualTo(200);
        // HR에게는 그대로 보인다
        assertThat(json(expect(interview.hr().get(interview.candidate()), 200)).path("row").path("decision")
                .asString()).isEqualTo("PASS");

        Interview other = interviewStage();
        expect(interviewer.get(other.candidate()), 403);
        expect(interviewer.get("/api/recruitments/" + other.recruitmentId() + "/applications/"
                + other.applicationId() + "/documents/RESUME"), 403);
        expect(interviewer.get("/api/recruitments/" + other.recruitmentId() + "/applications/"
                + other.applicationId() + "/photo"), 403);
    }

    private TestApi assigned(Interview interview) throws Exception {
        TestApi interviewer = newInterviewer(interview.hr(), "김지민");
        assign(interview, interviewer);
        return interviewer;
    }

    /** 인사는 따로 만든 면접관 계정, 실무는 interviewer로 배정한다 (HR 계정은 면접관으로 배정하지 않는다). */
    private void assign(Interview interview, TestApi interviewer) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("hrMemberId", newInterviewer(interview.hr(), "최인사").memberId().toString());
        body.put("practicalMemberId", interviewer.memberId().toString());
        body.put("expectedVersion", null);
        expect(interview.hr().put(interview.stage() + "/interview/assignment", body), 200);
    }

    /** 경로 변수에 이 면접의 값을 넣는다. 모르는 변수는 임의 UUID다. */
    private static String path(String pattern, Interview interview) {
        return pattern.replace("{stageId}", interview.stageId().toString())
                .replace("{recruitmentId}", interview.recruitmentId().toString())
                .replace("{applicationId}", interview.applicationId().toString())
                .replace("{type}", "RESUME")
                .replace("{group}", "PASS")
                .replaceAll("\\{[^}]+}", UUID.randomUUID().toString());
    }

    private static HttpResponse<String> send(TestApi api, RequestMethod method, String path) throws Exception {
        return switch (method) {
            case GET, HEAD, OPTIONS, TRACE -> api.get(path);
            case POST -> api.post(path, Map.of());
            case PUT -> api.put(path, Map.of());
            case PATCH -> api.patch(path, Map.of());
            case DELETE -> api.delete(path);
        };
    }
}
