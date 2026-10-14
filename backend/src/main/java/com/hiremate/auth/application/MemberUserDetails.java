package com.hiremate.auth.application;

import com.hiremate.auth.MemberPrincipal;
import java.util.Collection;
import java.util.List;
import org.springframework.security.core.CredentialsContainer;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

public class MemberUserDetails implements UserDetails, CredentialsContainer {

    private final MemberPrincipal principal;
    private String passwordHash;

    public MemberUserDetails(MemberPrincipal principal, String passwordHash) {
        this.principal = principal;
        this.passwordHash = passwordHash;
    }

    public MemberPrincipal principal() {
        return principal;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return List.of(new SimpleGrantedAuthority("ROLE_" + principal.role().name()));
    }

    @Override
    public String getPassword() {
        return passwordHash;
    }

    @Override
    public String getUsername() {
        return principal.email();
    }

    @Override
    public void eraseCredentials() {
        passwordHash = null;
    }
}
