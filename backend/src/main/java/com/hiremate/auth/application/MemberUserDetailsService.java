package com.hiremate.auth.application;

import com.hiremate.auth.domain.MemberRepository;
import java.util.Locale;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MemberUserDetailsService implements UserDetailsService {

    private final MemberRepository members;

    public MemberUserDetailsService(MemberRepository members) {
        this.members = members;
    }

    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) {
        return members.findByEmail(username.trim().toLowerCase(Locale.ROOT))
                .map(member -> new MemberUserDetails(member.toPrincipal(), member.getPasswordHash()))
                .orElseThrow(() -> new UsernameNotFoundException("Invalid credentials."));
    }
}
