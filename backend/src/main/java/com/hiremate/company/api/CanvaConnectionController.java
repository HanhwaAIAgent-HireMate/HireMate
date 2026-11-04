package com.hiremate.company.api;

import com.hiremate.company.CanvaConnectionService;
import com.hiremate.company.CanvaConnectionService.CanvaStatus;
import com.hiremate.global.AuthenticatedMember;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.constraints.Size;
import java.net.URI;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Validated
@RequestMapping("/api/companies/me/canva")
public class CanvaConnectionController {

    private final CanvaConnectionService canva;

    public CanvaConnectionController(CanvaConnectionService canva) {
        this.canva = canva;
    }

    @GetMapping
    public CanvaStatus status(AuthenticatedMember member, HttpSession session) {
        return canva.status(member, session);
    }

    @GetMapping("/designs")
    public List<CanvaConnectionService.CanvaDesign> designs(AuthenticatedMember member, HttpSession session,
            @RequestParam(defaultValue = "") @Size(max = 100) String query) {
        return canva.search(member, session, query);
    }

    @PostMapping("/authorization")
    public Authorization authorize(AuthenticatedMember member, HttpSession session) {
        return new Authorization(canva.authorize(member, session));
    }

    @GetMapping("/callback")
    public ResponseEntity<Void> callback(AuthenticatedMember member, HttpSession session,
            @RequestParam(required = false) String state, @RequestParam(required = false) String code,
            @RequestParam(required = false) String error) {
        return ResponseEntity.status(HttpStatus.SEE_OTHER)
                .location(URI.create(canva.callback(member, session, state, code, error))).build();
    }

    @PostMapping("/verify")
    public CanvaStatus verify(AuthenticatedMember member, HttpSession session) {
        return canva.verify(member, session);
    }

    @DeleteMapping
    public ResponseEntity<Void> disconnect(HttpSession session) {
        canva.disconnect(session);
        return ResponseEntity.noContent().build();
    }

    public record Authorization(String url) {
    }
}
