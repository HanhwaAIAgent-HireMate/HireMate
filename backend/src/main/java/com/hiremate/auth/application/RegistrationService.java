package com.hiremate.auth.application;

import com.hiremate.auth.MemberPrincipal;
import com.hiremate.auth.MemberRole;
import com.hiremate.auth.domain.Member;
import com.hiremate.auth.domain.MemberRepository;
import com.hiremate.company.CompanyInfo;
import com.hiremate.company.CompanyService;
import com.hiremate.global.ApiException;
import java.util.Locale;
import org.hibernate.exception.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {

    private final CompanyService companies;
    private final MemberRepository members;
    private final PasswordEncoder passwords;

    public RegistrationService(CompanyService companies, MemberRepository members, PasswordEncoder passwords) {
        this.companies = companies;
        this.members = members;
        this.passwords = passwords;
    }

    @Transactional
    public MemberPrincipal register(String companyName, String name, String email, String password) {
        String normalizedEmail = email.trim().toLowerCase(Locale.ROOT);
        if (members.findByEmail(normalizedEmail).isPresent()) {
            throw duplicateEmail();
        }
        String hash = passwords.encode(password);
        CompanyInfo company = companies.createCompany(companyName.trim());
        try {
            Member member = members.saveAndFlush(
                    new Member(company.companyId(), name.trim(), normalizedEmail, hash, MemberRole.HR));
            return member.toPrincipal();
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
