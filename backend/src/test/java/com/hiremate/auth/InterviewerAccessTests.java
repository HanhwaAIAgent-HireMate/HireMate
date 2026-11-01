package com.hiremate.auth;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.servlet.mvc.method.RequestMappingInfo;
import org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping;

/** 면접관 계정은 허용 목록의 경로만, 그것도 지정된 면접 전형(과 그 채용)에서만 연다. */
class InterviewerAccessTests extends IntegrationTest {

    /** 면접관에게 여는 경로. SecurityConfig의 면접관 규칙과 같아야 한다. 새 API는 여기에 넣지 않으면 막힌다. */
    static final Set<String> INTERVIEWER_ROUTES = Set.of(
            "GET /api/companies/me/profile",
            "GET /api/interviewer/stages",
            "GET /api/stages/{stageId}",
            "GET /api/stages/{stageId}/candidates",
            "GET /api/stages/{stageId}/candidates/{applicationId}",
            "GET /api/stages/{stageId}/candidates/{applicationId}/history",
            "GET /api/stages/{stageId}/candidates/{applicationId}/analysis",
            "GET /api/stages/{stageId}/candidates/{applicationId}/profile",
            "GET /api/stages/{stageId}/assessment/results/{applicationId}",
            "GET /api/stages/{stageId}/assessment/results/{applicationId}/file",
            "GET /api/recruitments/{recruitmentId}/applications/{applicationId}/documents/{type}",
            "GET /api/stages/{stageId}/candidates/{applicationId}/interview",
            "GET /api/stages/{stageId}/candidates/{applicationId}/interview/preparing",
            "GET /api/stages/{stageId}/interviewers");

    @Autowired
    @Qualifier("requestMappingHandlerMapping")
    private RequestMappingHandlerMapping mappings;

    @Test
    @DisplayName("지정된 면접관도 허용 목록 밖의 업무 API는 모두 403이다")
    void everyNonAllowlistedRouteIsForbiddenForInterviewers() throws Exception {
        Interview interview = interviewStage();
        TestApi interviewer = assigned(interview);
        List<String> opened = new ArrayList<>();
        for (Map.Entry<RequestMappingInfo, ?> entry : mappings.getHandlerMethods().entrySet()) {
            RequestMappingInfo info = entry.getKey();
            for (String pattern : info.getPatternValues()) {
                if (!pattern.startsWith("/api/") || pattern.startsWith("/api/auth/")
                        || pattern.startsWith("/api/public/")) {
                    continue;
                }
                Set<RequestMethod> methods = info.getMethodsCondition().getMethods();
                for (RequestMethod method : methods.isEmpty() ? Set.of(RequestMethod.GET) : methods) {
                    String route = method + " " + pattern;
                    if (INTERVIEWER_ROUTES.contains(route)) {
                        continue;
                    }
                    HttpResponse<String> response = send(interviewer, method, path(pattern, interview));
                    if (response.statusCode() != 403) {
                        opened.add(route + " → " + response.statusCode());
                    }
                }
            }
        }
        assertThat(opened).isEmpty();
    }

    @Test
    @DisplayName("허용 경로도 지정된 전형과 그 채용에서만 열리고, 다른 전형 · 채용은 403이다")
    void allowlistedRoutesNeedAssignment() throws Exception {
        Interview interview = interviewStage();
        TestApi interviewer = newInterviewer(interview.hr(), "김지민");
        String documents = "/api/recruitments/" + interview.recruitmentId() + "/applications/"
                + interview.applicationId() + "/documents/RESUME";

        expect(interviewer.get(interview.stage()), 403);
        expect(interviewer.get(interview.card()), 403);
        expect(interviewer.get(documents), 403);

        assign(interview, interviewer, "PRACTICAL");
        expect(interviewer.get(interview.stage()), 200);
        expect(interviewer.get(interview.stage() + "/candidates"), 200);
        expect(interviewer.get(interview.card()), 200);
        expect(interviewer.get(documents), 200);
        expect(interviewer.get("/api/companies/me/profile"), 200);

        Interview other = interviewStage();
        expect(interviewer.get(other.stage()), 403);
        expect(interviewer.get("/api/recruitments/" + other.recruitmentId() + "/applications/"
                + other.applicationId() + "/documents/RESUME"), 403);
        // 같은 채용이라도 지정되지 않은 서류 전형 경로는 열리지 않는다
        String document = json(expect(interview.hr().get(interview.stage()), 200)).path("steps").get(0)
                .path("stageId").asString();
        expect(interviewer.get("/api/stages/" + document), 403);
        // 쓰기는 이 PR에서 열지 않는다
        expect(interviewer.post(interview.card() + "/questions", Map.of("text", "질문")), 403);
    }

    private TestApi assigned(Interview interview) throws Exception {
        TestApi interviewer = newInterviewer(interview.hr(), "김지민");
        assign(interview, interviewer, "PRACTICAL");
        return interviewer;
    }

    private static void assign(Interview interview, TestApi interviewer, String role) throws Exception {
        expect(interview.hr().put(interview.stage() + "/interviewers", Map.of("slots", List.of(
                Map.of("role", role, "memberId", interviewer.memberId().toString())))), 200);
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
