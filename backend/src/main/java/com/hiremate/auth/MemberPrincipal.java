package com.hiremate.auth;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

public record MemberPrincipal(UUID memberId, UUID companyId, String name, String email, MemberRole role)
        implements Serializable {

    public MemberPrincipal {
        Objects.requireNonNull(memberId);
        Objects.requireNonNull(companyId);
        Objects.requireNonNull(name);
        Objects.requireNonNull(email);
        Objects.requireNonNull(role);
    }
}
