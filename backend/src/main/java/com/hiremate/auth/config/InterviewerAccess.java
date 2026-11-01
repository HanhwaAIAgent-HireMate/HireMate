package com.hiremate.auth.config;

import com.hiremate.auth.MemberPrincipal;
import com.hiremate.auth.MemberRole;
import com.hiremate.interview.InterviewAssignments;
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
 * 면접관에게 여는 경로의 권한. HR은 지금처럼 통과하고, 면접관은 경로의 전형(stageId)이나 채용(recruitmentId)에
 * 지정됐을 때만 통과한다. 전형 · 채용 변수가 없는 경로(기업 이름)는 같은 기업 계정이면 통과한다.
 */
@Component
class InterviewerAccess implements AuthorizationManager<RequestAuthorizationContext> {

    private final InterviewAssignments assignments;

    InterviewerAccess(InterviewAssignments assignments) {
        this.assignments = assignments;
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
            if (variables.containsKey("stageId")) {
                return new AuthorizationDecision(assignments.assigned(member.companyId(), member.memberId(),
                        UUID.fromString(variables.get("stageId"))));
            }
            if (variables.containsKey("recruitmentId")) {
                return new AuthorizationDecision(assignments.assignedInRecruitment(member.companyId(),
                        member.memberId(), UUID.fromString(variables.get("recruitmentId"))));
            }
        } catch (IllegalArgumentException invalidId) {
            return new AuthorizationDecision(false);
        }
        return new AuthorizationDecision(true);
    }
}
