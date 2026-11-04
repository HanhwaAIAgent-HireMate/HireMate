package com.hiremate.company;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.hiremate.company.application.CanvaClient;
import com.hiremate.company.application.CanvaClient.Tokens;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.global.JsonText;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

class CanvaConnectionServiceTests {

    private final CanvaClient client = mock(CanvaClient.class);
    private final CanvaConnectionService service = new CanvaConnectionService(client,
            "http://localhost:5173/api/companies/me/canva/callback", "http://localhost:5173/hr/settings/posting");
    private final MockHttpSession session = new MockHttpSession();
    private final Member member = new Member(UUID.randomUUID(), UUID.randomUUID(), "담당자", true);

    @Test
    void connectsOnlyAfterToolsAreVerifiedAndNeverReturnsTokens() {
        String state = begin();
        Tokens tokens = new Tokens("private-access", "private-refresh", Instant.now().plusSeconds(3600));
        when(client.exchange(anyString(), anyString(), anyString())).thenReturn(tokens);
        when(client.availableTools("private-access")).thenReturn(List.of("search-designs", "create-design"));
        assertThat(service.callback(member, session, state, "authorization-code", null)).endsWith("?canva=connected");
        assertThat(service.status(member, session).connected()).isTrue();
        assertThat(service.status(member, session).tools()).containsExactly("search-designs", "create-design");
        assertThat(JsonText.write(service.status(member, session))).doesNotContain("private-access", "private-refresh");
        assertThat(tokens.toString()).doesNotContain("private-access", "private-refresh");
        assertThatThrownBy(() -> service.callback(member, session, state, "authorization-code", null))
                .isInstanceOf(ApiException.class);
        service.disconnect(session);
        assertThat(service.status(member, session).connected()).isFalse();
    }

    @Test
    void wrongStateAndDifferentMembersCannotExchangeTheCode() {
        begin();
        assertThatThrownBy(() -> service.callback(member, session, "forged-state", "code", null))
                .isInstanceOf(ApiException.class);
        String state = begin();
        Member other = new Member(UUID.randomUUID(), member.companyId(), "다른 담당자", true);
        assertThatThrownBy(() -> service.callback(other, session, state, "code", null))
                .isInstanceOf(ApiException.class);
        String otherState = begin();
        Member otherCompany = new Member(member.memberId(), UUID.randomUUID(), "다른 기업", true);
        String lastState = otherState;
        assertThatThrownBy(() -> service.callback(otherCompany, session, lastState, "code", null))
                .isInstanceOf(ApiException.class);
        verify(client, never()).exchange(anyString(), anyString(), anyString());
    }

    @Test
    void deniedConsentDoesNotConnect() {
        String state = begin();
        assertThat(service.callback(member, session, state, null, "access_denied")).endsWith("?canva=denied");
        assertThat(service.status(member, session).connected()).isFalse();
        verify(client, never()).exchange(anyString(), anyString(), anyString());
    }

    @Test
    void failedToolVerificationDoesNotReportConnected() {
        String state = begin();
        when(client.exchange(anyString(), anyString(), anyString()))
                .thenReturn(new Tokens("access", "refresh", Instant.now().plusSeconds(3600)));
        when(client.availableTools("access")).thenThrow(new ApiException(
                org.springframework.http.HttpStatus.BAD_GATEWAY, "CANVA_UNAVAILABLE", "연결 실패"));
        assertThatThrownBy(() -> service.callback(member, session, state, "code", null))
                .isInstanceOf(ApiException.class);
        assertThat(service.status(member, session).connected()).isFalse();
    }

    @Test
    void refreshAndAccountIsolationAreEnforced() {
        String state = begin();
        when(client.exchange(anyString(), anyString(), anyString()))
                .thenReturn(new Tokens("old", "refresh", Instant.now().minusSeconds(1)));
        when(client.availableTools("old")).thenReturn(List.of("search-designs"));
        service.callback(member, session, state, "code", null);
        when(client.refresh("refresh"))
                .thenReturn(new Tokens("new", "rotated", Instant.now().plusSeconds(3600)));
        when(client.availableTools("new")).thenReturn(List.of("search-designs", "get-design"));
        assertThat(service.verify(member, session).tools()).containsExactly("search-designs", "get-design");
        assertThat(service.status(new Member(UUID.randomUUID(), member.companyId(), "다른 사용자", true), session)
                .connected()).isFalse();
        assertThat(service.status(member, session).connected()).isFalse();
    }

    private String begin() {
        when(client.configured()).thenReturn(true);
        when(client.authorizeUrl(anyString(), anyString(), anyString())).thenAnswer(call ->
                "https://www.canva.com/api/oauth/authorize?state=" + call.getArgument(1, String.class));
        String url = service.authorize(member, session);
        return URI.create(url).getQuery().substring("state=".length());
    }

    @Test
    void searchesOnlyTheConnectedMemberAndAcceptsNativeDesignIds() {
        String state = begin();
        when(client.exchange(anyString(), anyString(), anyString()))
                .thenReturn(new Tokens("access", "refresh", Instant.now().plusSeconds(3600)));
        when(client.availableTools("access")).thenReturn(List.of("search-designs", "get-design"));
        service.callback(member, session, state, "code", null);
        when(client.designTool(eq("access"), eq("search-designs"), anyMap()))
                .thenReturn(JsonText.read("{\"items\":[{\"design_id\":\"DA123456\",\"title\":\"채용형\"}]}",
                        tools.jackson.databind.JsonNode.class));
        when(client.designTool(eq("access"), eq("get-design"), anyMap()))
                .thenReturn(JsonText.read("{\"title\":\"채용형\",\"edit_url\":\"https://www.canva.com/d/example\"}",
                        tools.jackson.databind.JsonNode.class));
        assertThat(service.search(member, session, "채용")).containsExactly(
                new CanvaConnectionService.CanvaDesign("DA123456", "채용형", "https://www.canva.com/d/example", ""));
        Member other = new Member(UUID.randomUUID(), member.companyId(), "다른 담당자", true);
        assertThatThrownBy(() -> service.search(other, session, "채용")).isInstanceOf(ApiException.class);
    }

    @Test
    void capsSearchAtThreeUniqueCardsEvenWhenTheProviderReturnsMore() {
        String state = begin();
        when(client.exchange(anyString(), anyString(), anyString()))
                .thenReturn(new Tokens("access", "refresh", Instant.now().plusSeconds(3600)));
        when(client.availableTools("access")).thenReturn(List.of("search-designs"));
        service.callback(member, session, state, "code", null);
        when(client.designTool(eq("access"), eq("search-designs"), anyMap()))
                .thenReturn(JsonText.read("""
                        {"items":[{"design_id":"DA111111"},{"design_id":"DA111111"},{"design_id":"DA121212"},
                        {"design_id":"DA222222"},{"design_id":"DA333333"},{"design_id":"DA444444"}]}
                        """, tools.jackson.databind.JsonNode.class));
        when(client.designTool(eq("access"), eq("get-design"), anyMap()))
                .thenAnswer(invocation -> {
                    Map<String, Object> arguments = invocation.getArgument(2);
                    String id = arguments.get("design_id").toString();
                    return JsonText.read(JsonText.write(Map.of("title", id.equals("DA121212")
                            ? "DA111111" : id)), tools.jackson.databind.JsonNode.class);
                });
        assertThat(service.search(member, session, "금융")).extracting(CanvaConnectionService.CanvaDesign::id)
                .containsExactly("DA111111", "DA222222", "DA333333");
        verify(client).designTool("access", "search-designs", Map.of("query", "금융", "sort_by", "relevance",
                "limit", 12, "user_intent", "Find recruitment poster designs in my Canva library"));
    }

    @Test
    void importStopsWhenTheAccountCannotExportWithoutChangingTheSource() {
        String state = begin();
        when(client.exchange(anyString(), anyString(), anyString()))
                .thenReturn(new Tokens("access", "refresh", Instant.now().plusSeconds(3600)));
        when(client.availableTools("access")).thenReturn(List.of("copy-design", "export-design"));
        service.callback(member, session, state, "code", null);
        when(client.designTool(eq("access"), eq("copy-design"), anyMap()))
                .thenReturn(JsonText.read("{\"design_id\":\"DACOPY123\"}", tools.jackson.databind.JsonNode.class));
        when(client.designTool(eq("access"), eq("export-design"), anyMap()))
                .thenReturn(JsonText.read("{\"job\":{\"status\":\"failed\",\"urls\":[]}}",
                        tools.jackson.databind.JsonNode.class));
        when(client.designTool(eq("access"), eq("get-export-formats"), anyMap()))
                .thenReturn(JsonText.read("{\"formats\":[\"png\"]}", tools.jackson.databind.JsonNode.class));
        assertThatThrownBy(() -> service.importTemplate(member, session, "DA123456")).isInstanceOf(ApiException.class);
        verify(client, never()).designTool(anyString(), eq("start-editing-transaction"), anyMap());
        verify(client).designTool("access", "copy-design", Map.of("design_id", "DA123456", "page_numbers", List.of(1),
                "user_intent", "Make a private working copy for a recruitment poster"));
    }

    private record Member(UUID memberId, UUID companyId, String name, boolean hr) implements AuthenticatedMember {
    }

    @Test
    void importsNativeCanvaResponsesAndAlwaysDiscardsExtractionChanges() throws IOException {
        String state = begin();
        when(client.exchange(anyString(), anyString(), anyString()))
                .thenReturn(new Tokens("access", "refresh", Instant.now().plusSeconds(3600)));
        when(client.availableTools("access")).thenReturn(List.of("copy-design"));
        service.callback(member, session, state, "code", null);
        when(client.designTool(eq("access"), anyString(), anyMap())).thenAnswer(invocation -> {
            String response = switch (invocation.<String>getArgument(1)) {
                case "copy-design" -> "{\"design\":{\"id\":\"DACOPY123\",\"title\":\"금융 채용형\"}}";
                case "get-export-formats" -> "{\"formats\":{\"png\":{}}}";
                case "export-design" -> "{\"job\":{\"urls\":[\"https://export-download.canva.com/export\"]}}";
                case "start-editing-transaction" -> """
                        {"transaction":{"transaction_id":"draft"},
                         "pages":[{"dimension":{"width":794,"height":1123}}],
                         "richtexts":[{"element_id":"source-title","page_index":1,
                         "regions":[{"text":"원본 제목"}],"containerElement":{
                         "position":{"left":40,"top":80},"dimension":{"width":500,"height":100}}},
                         {"element_id":"source-logo-label","page_index":1,"regions":[{"text":"로고 공간"}],
                          "containerElement":{"position":{"left":650,"top":70},"dimension":{"width":60,"height":18}}}],
                         "fills":[{"element_id":"source-frame","page_index":1,"containerElement":{
                           "position":{"left":610,"top":36},"dimension":{"width":138,"height":87}}},
                          {"element_id":"source-page","page_index":1,"containerElement":{
                           "position":{"left":0,"top":0},"dimension":{"width":794,"height":1123}}}]}
                        """;
                case "perform-editing-operations" ->
                        "{\"thumbnails\":[{\"url\":\"https://export-download.canva.com/preview\"}]}";
                default -> "{}";
            };
            return JsonText.read(response, tools.jackson.databind.JsonNode.class);
        });
        ByteArrayOutputStream image = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(20, 30, BufferedImage.TYPE_INT_RGB), "png", image);
        when(client.previewImage(anyString())).thenReturn(image.toByteArray());
        var imported = service.importTemplate(member, session, "DA123456");
        assertThat(imported.name()).isEqualTo("금융 채용형");
        assertThat(imported.background()).startsWith("data:image/jpeg;base64,");
        assertThat(imported.regions()).hasSize(1);
        assertThat(imported.regions().getFirst().text()).isEqualTo("원본 제목");
        verify(client).designTool("access", "export-design", Map.of("design_id", "DACOPY123",
                "format", Map.of("type", "png", "export_quality", "regular", "lossless", false),
                "user_intent", "Verify this design can be exported under the current account without upgrading"));
        verify(client).designTool(eq("access"), eq("cancel-editing-transaction"), anyMap());
        verify(client).designTool(eq("access"), eq("perform-editing-operations"), argThat(arguments ->
                arguments.get("operations").toString().contains("source-frame")
                && !arguments.get("operations").toString().contains("source-page")));
        verify(client, never()).designTool(anyString(), eq("commit-editing-transaction"), anyMap());
    }
}
