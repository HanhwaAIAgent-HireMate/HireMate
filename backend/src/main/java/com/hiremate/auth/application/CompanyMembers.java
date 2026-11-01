package com.hiremate.auth.application;

import com.hiremate.auth.MemberRole;
import com.hiremate.auth.domain.Member;
import com.hiremate.auth.domain.MemberRepository;
import com.hiremate.global.CompanyMember;
import com.hiremate.global.MemberDirectory;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 업무 모듈에 공개하는 기업 계정 조회. */
@Service
public class CompanyMembers implements MemberDirectory {

    private final MemberRepository members;

    public CompanyMembers(MemberRepository members) {
        this.members = members;
    }

    @Override
    @Transactional(readOnly = true)
    public List<CompanyMember> members(UUID companyId) {
        return members.findByCompanyIdOrderByCreatedAt(companyId).stream().map(CompanyMembers::toMember).toList();
    }

    @Override
    @Transactional(readOnly = true)
    public Optional<CompanyMember> find(UUID companyId, UUID memberId) {
        return members.findByIdAndCompanyId(memberId, companyId).map(CompanyMembers::toMember);
    }

    private static CompanyMember toMember(Member member) {
        return new CompanyMember(member.getId(), member.getName(), member.getEmail(),
                member.getRole() == MemberRole.HR);
    }
}
