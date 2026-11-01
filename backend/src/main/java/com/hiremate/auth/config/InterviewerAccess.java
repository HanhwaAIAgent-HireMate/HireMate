package com.hiremate.auth.config;

import com.hiremate.auth.MemberPrincipal;
import com.hiremate.auth.MemberRole;
import com.hiremate.interview.InterviewSessions;
import java.util.Map;
import java.util.UUID;
import java.util.function.Supplier;
import org.jspecify.annotations.Nullable;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.authorization.AuthorizationResult;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.access.intercept.RequestAuthorizationContext;
import org.springframework.stereotype.Component;

/**
 * 면접관 모드의 경로 권한. HR은 지금처럼 통과하고, 면접관은 경로의 지원자(applicationId) 면접에 배정됐을 때만
 * 통과한다. 전형 경로는 그 전형의 면접에, 채용 경로(지원 문서)는 그 지원자의 면접 하나에라도 배정돼야 한다.
 * 지원자가 없는 Chat 탭 경로는 그 전형에서 한 명이라도 배정돼야 한다.
 */
@Component
class InterviewerAccess implements AuthorizationManager<RequestAuthorizationContext> {

    private final InterviewSessions sessions;

    InterviewerAccess(InterviewSessions sessions) {
        this.sessions = sessions;
    }

    @Override
    public AuthorizationResult authorize(Supplier<? extends @Nullable Authentication> authentication,
            RequestAuthorizationContext context) {
        Authentication current = authentication.get();
        if (current == null || !current.isAuthenticated()
                || !(current.getPrincipal() instanceof MemberPrincipal member)) {
            return new AuthorizationDecision(false);
        }
        if (member.role() == MemberRole.HR) {
            return new AuthorizationDecision(true);
        }
        Map<String, String> variables = context.getVariables();
        try {
            String stageId = variables.get("stageId");
            String applicationId = variables.get("applicationId");
            if (stageId != null && applicationId != null) {
                return new AuthorizationDecision(sessions.assigned(member.companyId(), member.memberId(),
                        UUID.fromString(stageId), UUID.fromString(applicationId)));
            }
            if (stageId != null) {
                // Chat 탭: 이 전형에서 배정된 면접관만. 탭이 자기 것인지는 탭 서비스가 확인한다
                return new AuthorizationDecision(sessions.assignedInStage(member.companyId(), member.memberId(),
                        UUID.fromString(stageId)));
            }
            return new AuthorizationDecision(applicationId != null && sessions.assignedToApplication(
                    member.companyId(), member.memberId(), UUID.fromString(applicationId)));
        } catch (IllegalArgumentException invalidId) {
            return new AuthorizationDecision(false);
        }
    }
}
