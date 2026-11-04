package com.hiremate.company;

import com.hiremate.company.application.CanvaClient;
import com.hiremate.company.application.CanvaClient.Tokens;
import com.hiremate.global.ApiException;
import com.hiremate.global.AuthenticatedMember;
import com.hiremate.global.JsonText;
import jakarta.servlet.http.HttpSession;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import javax.imageio.ImageIO;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import tools.jackson.databind.JsonNode;

/** HR 본인의 서버 세션 안에서만 Canva OAuth 권한을 보관한다. 다른 사용자·기업과 공유하지 않는다. */
@Service
public class CanvaConnectionService {

    private static final String PENDING = "canva.oauth.pending";
    private static final String CONNECTION = "canva.oauth.connection";
    private static final SecureRandom RANDOM = new SecureRandom();
    private final CanvaClient client;
    private final String redirect;
    private final String returnUri;

    public CanvaConnectionService(CanvaClient client,
            @Value("${CANVA_REDIRECT_URI:http://127.0.0.1:5173/api/companies/me/canva/callback}") String redirect,
            @Value("${CANVA_RETURN_URI:http://127.0.0.1:5173/hr/settings/posting}") String returnUri) {
        this.client = client;
        this.redirect = redirect;
        this.returnUri = returnUri;
    }

    public CanvaStatus status(AuthenticatedMember member, HttpSession session) {
        Connection saved = connection(member, session);
        return new CanvaStatus(client.configured(), saved != null, redirect, saved == null ? List.of() : saved.tools());
    }

    public String authorize(AuthenticatedMember member, HttpSession session) {
        String state = random();
        String verifier = random();
        String url = client.authorizeUrl(redirect, state, challenge(verifier));
        session.setAttribute(PENDING, JsonText.write(new Pending(state, verifier, member.companyId(), member.memberId(),
                Instant.now().plusSeconds(600))));
        return url;
    }

    public String callback(AuthenticatedMember member, HttpSession session, String state, String code, String error) {
        Pending pending = JsonText.read((String) session.getAttribute(PENDING), Pending.class);
        session.removeAttribute(PENDING);
        if (pending == null || state == null || !equal(pending.state(), state)
                || !pending.expiresAt().isAfter(Instant.now()) || !pending.companyId().equals(member.companyId())
                || !pending.memberId().equals(member.memberId())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "CANVA_INVALID_STATE",
                    "Canva 연결 요청이 만료됐거나 일치하지 않아요. 연결을 다시 시작해 주세요.");
        }
        if (error != null) {
            return returnUri + "?canva=denied";
        }
        if (code == null || code.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "CANVA_INVALID_CODE", "Canva 승인이 완료되지 않았어요.");
        }
        Tokens tokens = client.exchange(code, pending.verifier(), redirect);
        List<String> tools = client.availableTools(tokens.accessToken());
        session.setAttribute(CONNECTION, JsonText.write(new Connection(member.companyId(), member.memberId(),
                tokens, tools)));
        return returnUri + "?canva=connected";
    }

    public CanvaStatus verify(AuthenticatedMember member, HttpSession session) {
        Connection saved = connection(member, session);
        if (saved == null) {
            throw new ApiException(HttpStatus.CONFLICT, "CANVA_NOT_CONNECTED", "먼저 Canva 계정을 연결해 주세요.");
        }
        Tokens tokens = saved.tokens();
        try {
            if (!tokens.expiresAt().isAfter(Instant.now().plusSeconds(60))) {
                if (tokens.refreshToken() == null || tokens.refreshToken().isBlank()) {
                    throw new ApiException(HttpStatus.CONFLICT, "CANVA_NOT_CONNECTED", "Canva를 다시 연결해 주세요.");
                }
                tokens = client.refresh(tokens.refreshToken());
                // 회전된 refresh token은 다음 조회가 실패하더라도 먼저 보존한다.
                session.setAttribute(CONNECTION, JsonText.write(new Connection(member.companyId(), member.memberId(),
                        tokens, saved.tools())));
            }
            List<String> tools = client.availableTools(tokens.accessToken());
            session.setAttribute(CONNECTION, JsonText.write(new Connection(member.companyId(), member.memberId(),
                    tokens, tools)));
            return status(member, session);
        } catch (ApiException exception) {
            session.removeAttribute(CONNECTION);
            throw exception;
        }
    }

    public void disconnect(HttpSession session) {
        session.removeAttribute(CONNECTION);
        session.removeAttribute(PENDING);
    }

    public List<CanvaDesign> search(AuthenticatedMember member, HttpSession session, String query) {
        Map<String, Object> arguments = query.isBlank()
                ? Map.of("sort_by", "modified_descending", "limit", 12,
                        "user_intent", "Find recruitment poster designs in my Canva library")
                : Map.of("query", query, "sort_by", "relevance", "limit", 12,
                        "user_intent", "Find recruitment poster designs in my Canva library");
        JsonNode result = call(member, session, "search-designs", arguments);
        JsonNode rows = result.has("results") ? result.path("results") : result.path("items");
        List<CanvaDesign> designs = new ArrayList<>();
        java.util.Set<String> seen = new java.util.HashSet<>();
        java.util.Set<String> titles = new java.util.HashSet<>();
        int inspected = 0;
        for (JsonNode row : rows) {
            if (++inspected > 12) {
                break;
            }
            String id = row.path("id").asString(row.path("design_id").asString(""));
            if (!id.matches("D[A-Za-z0-9_-]{5,79}") || !seen.add(id)) {
                continue;
            }
            JsonNode metadata = call(member, session, "get-design", Map.of("design_id", id,
                    "user_intent", "Preview a recruitment design before importing it"));
            JsonNode design = metadata.has("design") ? metadata.path("design") : metadata;
            String title = design.path("title").asString(row.path("title").asString("Canva 디자인"));
            String normalized = title.replaceAll("\\s+", "").toLowerCase(java.util.Locale.ROOT);
            if (!titles.add(normalized)) {
                continue;
            }
            designs.add(new CanvaDesign(id, title,
                    design.path("urls").path("edit_url").asString(design.path("edit_url")
                            .asString(row.path("edit_url").asString(row.path("url").asString("")))),
                    design.path("thumbnail").path("url").asString("")));
            if (designs.size() == 3) {
                break;
            }
        }
        return List.copyOf(designs);
    }

    private JsonNode call(AuthenticatedMember member, HttpSession session, String tool, Map<String, Object> arguments) {
        Connection saved = connection(member, session);
        if (saved == null) {
            throw new ApiException(HttpStatus.CONFLICT, "CANVA_NOT_CONNECTED", "먼저 Canva 계정을 연결해 주세요.");
        }
        if (!saved.tokens().expiresAt().isAfter(Instant.now().plusSeconds(60))) {
            verify(member, session);
            saved = connection(member, session);
        }
        return client.designTool(saved.tokens().accessToken(), tool, arguments);
    }

    public record CanvaDesign(String id, String name, String editUrl, String thumbnailUrl) {
    }

    public CanvaTemplate importTemplate(AuthenticatedMember member, HttpSession session, String designId) {
        JsonNode copied = call(member, session, "copy-design", Map.of("design_id", designId,
                "page_numbers", List.of(1), "user_intent", "Make a private working copy for a recruitment poster"));
        JsonNode copy = copied.has("design") ? copied.path("design") : copied;
        String copyId = copy.path("id").asString(copy.path("design_id").asString(""));
        if (copyId.isBlank()) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "CANVA_COPY_FAILED", "Canva 작업본을 만들지 못했어요.");
        }
        JsonNode formats = call(member, session, "get-export-formats", Map.of("design_id", copyId,
                "user_intent", "Check export formats available to this account"));
        if (!supportsPng(formats)) {
            throw new ApiException(HttpStatus.CONFLICT, "CANVA_EXPORT_UNAVAILABLE",
                    "이 디자인은 현재 계정에서 PNG로 가져올 수 없어요.");
        }
        JsonNode exported = call(member, session, "export-design", Map.of("design_id", copyId,
                "format", Map.of("type", "png", "export_quality", "regular", "lossless", false),
                "user_intent", "Verify this design can be exported under the current account without upgrading"));
        JsonNode exportJob = exported.has("job") ? exported.path("job") : exported;
        if (exportJob.path("urls").isEmpty()) {
            throw new ApiException(HttpStatus.CONFLICT, "CANVA_EXPORT_UNAVAILABLE",
                    "현재 계정에서 내보낼 수 있는 디자인만 가져올 수 있어요. 유료 요소와 이용 한도를 확인해 주세요.");
        }
        JsonNode opened = call(member, session, "start-editing-transaction", Map.of("design_id", copyId,
                "user_intent", "Extract the poster background without changing the original design"));
        String transaction = opened.path("transaction").path("transaction_id")
                .asString(opened.path("transaction_id").asString(""));
        if (transaction.isBlank()) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "CANVA_READ_FAILED", "디자인 영역을 읽지 못했어요.");
        }
        try {
            List<Map<String, Object>> operations = new ArrayList<>();
            for (JsonNode text : opened.path("richtexts")) {
                if (text.path("page_index").asInt(1) == 1) {
                    operations.add(Map.of("type", "delete_element", "element_id", text.path("element_id").asString()));
                }
            }
            for (JsonNode fill : opened.path("fills")) {
                if (fill.path("page_index").asInt(1) == 1 && isLogoPlaceholder(fill, opened)) {
                    operations.add(Map.of("type", "delete_element", "element_id", fill.path("element_id").asString()));
                }
            }
            JsonNode preview = operations.isEmpty() ? opened : call(member, session, "perform-editing-operations",
                    Map.of("transaction_id", transaction, "page_index", 1, "operations", operations,
                            "user_intent", "Temporarily remove source wording before inserting current job content"));
            String image = preview.path("thumbnails").path(0).path("url").asString("");
            if (image.isBlank()) {
                throw new ApiException(HttpStatus.BAD_GATEWAY, "CANVA_PREVIEW_FAILED", "배경 미리보기를 받지 못했어요.");
            }
            List<CanvaRegion> regions = new ArrayList<>();
            for (JsonNode text : opened.path("richtexts")) {
                if (text.path("page_index").asInt(1) != 1) {
                    continue;
                }
                StringBuilder wording = new StringBuilder();
                for (JsonNode run : text.path("regions")) {
                    wording.append(run.path("text").asString(""));
                }
                if (logoLabel(wording.toString())) {
                    continue;
                }
                JsonNode box = text.path("containerElement");
                regions.add(new CanvaRegion(text.path("element_id").asString(), wording.toString(),
                        box.path("position").path("left").asDouble(), box.path("position").path("top").asDouble(),
                        box.path("dimension").path("width").asDouble(),
                        box.path("dimension").path("height").asDouble()));
            }
            JsonNode dimensions = opened.path("pages").path(0).path("dimension");
            return new CanvaTemplate(designId, copy.path("title").asString("Canva 채용형"),
                    copy.path("urls").path("edit_url").asString(""), compactImage(client.previewImage(image)),
                    dimensions.path("width").asDouble(794), dimensions.path("height").asDouble(1123), regions);
        } finally {
            call(member, session, "cancel-editing-transaction", Map.of("transaction_id", transaction,
                    "user_intent", "Discard extraction-only draft changes; preserve the working copy"));
        }
    }

    private static boolean logoLabel(String text) {
        return java.util.Set.of("로고", "로고공간", "회사로고", "logo", "logohere", "companylogo")
                .contains(text.replaceAll("\\s+", "").toLowerCase(java.util.Locale.ROOT));
    }

    private static boolean isLogoPlaceholder(JsonNode fill, JsonNode opened) {
        JsonNode box = fill.path("containerElement");
        double left = box.path("position").path("left").asDouble();
        double top = box.path("position").path("top").asDouble();
        double width = box.path("dimension").path("width").asDouble();
        double height = box.path("dimension").path("height").asDouble();
        JsonNode page = opened.path("pages").path(0).path("dimension");
        if (width <= 0 || height <= 0 || width > page.path("width").asDouble() * .35
                || height > page.path("height").asDouble() * .2 || top > page.path("height").asDouble() * .25) {
            return false;
        }
        for (JsonNode text : opened.path("richtexts")) {
            StringBuilder label = new StringBuilder();
            for (JsonNode run : text.path("regions")) {
                label.append(run.path("text").asString(""));
            }
            JsonNode anchor = text.path("containerElement");
            double x = anchor.path("position").path("left").asDouble()
                    + anchor.path("dimension").path("width").asDouble() / 2;
            double y = anchor.path("position").path("top").asDouble()
                    + anchor.path("dimension").path("height").asDouble() / 2;
            if (logoLabel(label.toString()) && x >= left && x <= left + width && y >= top && y <= top + height) {
                return true;
            }
        }
        return false;
    }

    private static String compactImage(byte[] bytes) {
        try {
            BufferedImage source = ImageIO.read(new ByteArrayInputStream(bytes));
            if (source == null || source.getWidth() > 5000 || source.getHeight() > 10000) {
                throw new IOException("Unsupported image");
            }
            int width = Math.min(900, source.getWidth());
            int height = (int) ((long) source.getHeight() * width / source.getWidth());
            BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
            var graphics = image.createGraphics();
            try {
                graphics.setColor(Color.WHITE);
                graphics.fillRect(0, 0, width, height);
                graphics.drawImage(source, 0, 0, width, height, null);
            } finally {
                graphics.dispose();
            }
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            ImageIO.write(image, "jpg", output);
            if (output.size() > 90000) {
                throw new IOException("Image too large");
            }
            return "data:image/jpeg;base64," + Base64.getEncoder().encodeToString(output.toByteArray());
        } catch (IOException exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "CANVA_IMAGE_FAILED", "가져올 배경 이미지를 준비하지 못했어요.");
        }
    }

    private static boolean supportsPng(JsonNode value) {
        if (value.has("png")) {
            return true;
        }
        if (value.isString()) {
            return "png".equalsIgnoreCase(value.asString());
        }
        for (JsonNode child : value) {
            if (supportsPng(child)) {
                return true;
            }
        }
        return false;
    }

    public record CanvaTemplate(String id, String name, String editUrl, String background,
            double width, double height, List<CanvaRegion> regions) {
    }

    public record CanvaRegion(String id, String text, double left, double top, double width, double height) {
    }

    private Connection connection(AuthenticatedMember member, HttpSession session) {
        Connection saved = JsonText.read((String) session.getAttribute(CONNECTION), Connection.class);
        if (saved != null && (!saved.companyId().equals(member.companyId())
                || !saved.memberId().equals(member.memberId()))) {
            disconnect(session);
            return null;
        }
        return saved;
    }

    private static String random() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static String challenge(String verifier) {
        try {
            return Base64.getUrlEncoder().withoutPadding()
                    .encodeToString(MessageDigest.getInstance("SHA-256")
                            .digest(verifier.getBytes(StandardCharsets.US_ASCII)));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is required", exception);
        }
    }

    private static boolean equal(String first, String second) {
        return MessageDigest.isEqual(first.getBytes(StandardCharsets.UTF_8), second.getBytes(StandardCharsets.UTF_8));
    }

    public record CanvaStatus(boolean configured, boolean connected, String redirectUri, List<String> tools) {
    }

    private record Pending(String state, String verifier, UUID companyId, UUID memberId, Instant expiresAt) {
    }

    private record Connection(UUID companyId, UUID memberId, Tokens tokens, List<String> tools) {
    }
}
