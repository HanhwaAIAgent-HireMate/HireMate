package com.hiremate.auth;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.hiremate.global.ApiException;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

class AuthAccessTests {

    private final AuthAccess access = new AuthAccess();

    @AfterEach
    void clearContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void sameCompanyHrCanEnterAndReceivesPersistedIdentity() {
        MemberPrincipal hr = member(MemberRole.HR);
        authenticate(hr);
        access.requireHr();
        access.requireCompany(hr.companyId());
        assertThat(access.currentMember()).isEqualTo(hr);
    }

    @Test
    void otherCompanyIsDenied() {
        authenticate(member(MemberRole.HR));
        assertThatThrownBy(() -> access.requireCompany(UUID.randomUUID()))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.status()).isEqualTo(HttpStatus.FORBIDDEN));
    }

    @Test
    void missingResourceCompanyIsDenied() {
        authenticate(member(MemberRole.HR));
        assertThatThrownBy(() -> access.requireCompany(null))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.status()).isEqualTo(HttpStatus.FORBIDDEN));
    }

    @Test
    void interviewerCannotEnterHrOrSameCompanyBusiness() {
        MemberPrincipal interviewer = member(MemberRole.INTERVIEWER);
        authenticate(interviewer);
        assertThat(access.currentMember()).isEqualTo(interviewer);
        assertThatThrownBy(access::requireHr).isInstanceOfSatisfying(ApiException.class,
                exception -> assertThat(exception.status()).isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> access.requireCompany(interviewer.companyId()))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.status()).isEqualTo(HttpStatus.FORBIDDEN));
    }

    @Test
    void anonymousCannotPassAnyAccessCheck() {
        assertUnauthenticated();
    }

    @Test
    void wrongPrincipalCannotPassAnyAccessCheck() {
        authenticate("unexpected-principal");
        assertUnauthenticated();
    }

    @Test
    void unauthenticatedMemberTokenCannotPassAnyAccessCheck() {
        SecurityContextHolder.getContext().setAuthentication(
                UsernamePasswordAuthenticationToken.unauthenticated(member(MemberRole.HR), null));
        assertUnauthenticated();
    }

    private void assertUnauthenticated() {
        assertThatThrownBy(access::currentMember).isInstanceOfSatisfying(ApiException.class,
                exception -> assertThat(exception.status()).isEqualTo(HttpStatus.UNAUTHORIZED));
        assertThatThrownBy(access::requireHr).isInstanceOfSatisfying(ApiException.class,
                exception -> assertThat(exception.status()).isEqualTo(HttpStatus.UNAUTHORIZED));
        assertThatThrownBy(() -> access.requireCompany(UUID.randomUUID()))
                .isInstanceOfSatisfying(ApiException.class,
                        exception -> assertThat(exception.status()).isEqualTo(HttpStatus.UNAUTHORIZED));
    }

    private MemberPrincipal member(MemberRole role) {
        return new MemberPrincipal(UUID.randomUUID(), UUID.randomUUID(), "Test member", "test@example.com", role);
    }

    private void authenticate(Object principal) {
        SecurityContextHolder.getContext().setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(principal, null, List.of()));
    }
}
