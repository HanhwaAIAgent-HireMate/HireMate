package com.hiremate.auth;

import com.hiremate.global.ApiException;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

/** 인증 진입 계층에서 사용한다. 업무 서비스에는 인증된 companyId를 전달한다. */
@Component
public class AuthAccess {

    public MemberPrincipal currentMember() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof MemberPrincipal member)) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED", "Authentication is required.");
        }
        return member;
    }

    public void requireHr() {
        if (currentMember().role() != MemberRole.HR) {
            throw new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN", "Access is denied.");
        }
    }

    public void requireCompany(UUID resourceCompanyId) {
        requireHr();
        if (!currentMember().companyId().equals(resourceCompanyId)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN", "Access is denied.");
        }
    }
}
