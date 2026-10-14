package com.hiremate.auth.api;

import com.hiremate.auth.MemberPrincipal;
import com.hiremate.auth.MemberRole;
import java.util.UUID;

public record MemberResponse(UUID memberId, UUID companyId, String name, String email, MemberRole role) {

    public static MemberResponse from(MemberPrincipal member) {
        return new MemberResponse(member.memberId(), member.companyId(), member.name(), member.email(), member.role());
    }
}
