package com.hiremate.auth.application;

import com.hiremate.auth.MemberRole;
import com.hiremate.auth.domain.Member;
import com.hiremate.auth.domain.MemberRepository;
import com.hiremate.global.ApiException;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * HR이 기업 설정에서 면접관 계정을 만든다. 비밀번호는 HR이 면접관에게 직접 알려 준다.
 * 만든 계정은 면접 배정 후보(InterviewMemberDirectory)에 바로 보인다.
 */
@Service
public class InterviewerAccountService {

    private final MemberRepository members;
    private final PasswordEncoder passwords;

    public InterviewerAccountService(MemberRepository members, PasswordEncoder passwords) {
        this.members = members;
        this.passwords = passwords;
    }

    @Transactional(readOnly = true)
    public List<Member> interviewers(UUID companyId) {
        return members.findByCompanyIdOrderByName(companyId).stream()
                .filter(member -> member.getRole() == MemberRole.INTERVIEWER).toList();
    }

    @Transactional
    public Member create(UUID companyId, String name, String email, String password) {
        String normalizedEmail = email.trim().toLowerCase(Locale.ROOT);
        if (members.findByEmail(normalizedEmail).isPresent()) {
            throw duplicateEmail();
        }
        try {
            return members.saveAndFlush(new Member(companyId, name.trim(), normalizedEmail, passwords.encode(password),
                    MemberRole.INTERVIEWER));
        } catch (DataIntegrityViolationException exception) {
            if (exception.getCause() instanceof ConstraintViolationException violation
                    && "members_email_key".equals(violation.getConstraintName())) {
                throw duplicateEmail();
            }
            throw exception;
        }
    }

    private ApiException duplicateEmail() {
        return new ApiException(HttpStatus.CONFLICT, "EMAIL_ALREADY_EXISTS", "The email is already registered.");
    }
}
