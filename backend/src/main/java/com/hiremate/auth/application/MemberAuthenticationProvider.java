package com.hiremate.auth.application;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.password.PasswordEncoder;

/** 표준 비밀번호 검증 뒤 세션에 저장되는 principal에서 비밀번호를 제거한다. */
public class MemberAuthenticationProvider extends DaoAuthenticationProvider {

    public MemberAuthenticationProvider(MemberUserDetailsService members, PasswordEncoder passwords) {
        super(members);
        setPasswordEncoder(passwords);
    }

    @Override
    protected Authentication createSuccessAuthentication(Object principal, Authentication authentication,
            UserDetails user) {
        Authentication verified = super.createSuccessAuthentication(principal, authentication, user);
        MemberUserDetails member = (MemberUserDetails) user;
        UsernamePasswordAuthenticationToken result = UsernamePasswordAuthenticationToken.authenticated(
                member.principal(), null, verified.getAuthorities());
        result.setDetails(verified.getDetails());
        member.eraseCredentials();
        return result;
    }
}
