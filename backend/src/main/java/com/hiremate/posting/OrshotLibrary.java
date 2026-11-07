package com.hiremate.posting;

import com.hiremate.global.ApiException;
import io.swagger.v3.oas.annotations.media.Schema;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.time.Duration;
import java.util.Base64;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import javax.imageio.ImageIO;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import tools.jackson.databind.JsonNode;

/** 관리자가 승인한 공용 Orshot 원본만 조회한다. 검색에는 생성 크레딧을 쓰지 않는다. */
@Service
public class OrshotLibrary {
    private final WebClient http;
    private final String key;
    private final List<Long> ids;
    private final Map<Long, OrshotTemplate> rendered = new ConcurrentHashMap<>();

    public OrshotLibrary(WebClient.Builder builder, @Value("${ORSHOT_API_KEY:}") String key,
            @Value("${ORSHOT_TEMPLATE_IDS:}") String templateIds) {
        this.http = builder.baseUrl("https://api.orshot.com")
                .codecs(config -> config.defaultCodecs().maxInMemorySize(4 * 1024 * 1024)).build();
        this.key = key.strip();
        this.ids = java.util.Arrays.stream(templateIds.split(",")).map(String::strip)
                .filter(id -> id.matches("[1-9][0-9]{0,8}")).map(Long::valueOf).distinct().limit(15).toList();
    }

    public List<PosterProposal.FreeTemplate> search(String query, Set<String> excluded) {
        return search(query, excluded, null);
    }

    public List<PosterProposal.FreeTemplate> search(String query, Set<String> excluded, Boolean motion) {
        requireConfigured();
        try {
            return ids.stream().filter(id -> !excluded.contains("orshot:" + id))
                    .map(this::accessibleTemplate).flatMap(Optional::stream)
                    .filter(node -> node.path("canvas_width").asInt() >= 300)
                    .filter(node -> motion == null || motion == hasMotion(node))
                    .sorted(Comparator.comparingInt((JsonNode node) -> score(node, query)).reversed())
                    .limit(3).map(node -> new PosterProposal.FreeTemplate("orshot:" + node.path("id").asLong(),
                            node.path("name").asString("Orshot 디자인").substring(0,
                                    Math.min(100, node.path("name").asString("Orshot 디자인").length())),
                            "https://orshot.com/templates/", "Orshot 계정 디자인",
                            "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"600\" height=\"900\"/>",
                            node.path("thumbnail_url").asString(""))).toList();
        } catch (RuntimeException exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "ORSHOT_UNAVAILABLE", "Orshot 원본을 조회하지 못했어요.");
        }
    }

    private static boolean hasMotion(JsonNode node) {
        return node.path("pages_data").path(0).path("has_motion").asBoolean()
                || !node.path("pages_data").path(0).path("video_thumbnail_url").asString("").isEmpty();
    }

    public OrshotTemplate importTemplate(long id) {
        requireConfigured();
        if (!ids.contains(id)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "ORSHOT_TEMPLATE_NOT_ALLOWED", "허용된 원본을 선택해 주세요.");
        }
        OrshotTemplate cached = rendered.get(id);
        if (cached != null) {
            return cached;
        }
        try {
            JsonNode metadata = template(id);
            Map<String, Object> modifications = new LinkedHashMap<>();
            for (JsonNode field : metadata.path("modifications")) {
                String name = field.path("key").asString("");
                if (name.matches("[a-zA-Z0-9_-]{1,100}") && field.path("type").asString("").equals("text")) {
                    modifications.put(name + ".opacity", 0);
                }
                if (name.equals("cta_bg_color") && field.path("type").asString("").equals("fill")) {
                    modifications.put(name + ".opacity", 0);
                    modifications.put(name, "transparent");
                    modifications.put(name + ".fill", "transparent");
                }
            }
            if (modifications.isEmpty()) {
                throw new IllegalArgumentException("No removable source text");
            }
            int sourceWidth = metadata.path("canvas_width").asInt();
            int sourceHeight = metadata.path("canvas_height").asInt();
            if (sourceWidth < 300 || sourceHeight < 300 || sourceWidth > 6000 || sourceHeight > 6000) {
                throw new IllegalArgumentException("Invalid source dimensions");
            }
            int renderHeight = Math.max(1, (int) Math.round(sourceHeight * 600.0 / sourceWidth));
            // 현재 회사·공고 문구나 로고는 보내지 않는다. 원본의 배경만 1회 렌더링한다.
            JsonNode response = http.post().uri("/v1/studio/render")
                    .headers(headers -> headers.setBearerAuth(key))
                    .bodyValue(Map.of("templateId", id, "modifications", modifications,
                            "response", Map.of("type", "base64", "format", "jpg", "quality", 78,
                                    "width", 600, "height", renderHeight)))
                    .retrieve().bodyToMono(JsonNode.class).block(Duration.ofSeconds(60));
            JsonNode data = response == null ? null : response.path("data");
            if (data != null && data.isArray()) {
                data = data.path(0);
            }
            String image = data == null ? "" : data.path("content").asString("");
            Header header = compactHeader(image);
            String motion = null;
            if (hasMotion(metadata)) {
                JsonNode video = http.post().uri("/v1/studio/render")
                        .headers(headers -> headers.setBearerAuth(key))
                        .bodyValue(Map.of("templateId", id, "modifications", modifications,
                                "response", Map.of("type", "url", "format", "mp4", "width", 600,
                                        "height", renderHeight),
                                "videoOptions", Map.of("muted", true, "fps", 24)))
                        .retrieve().bodyToMono(JsonNode.class).block(Duration.ofSeconds(90));
                JsonNode videoData = video == null ? null : video.path("data");
                if (videoData != null && videoData.isArray()) {
                    videoData = videoData.path(0);
                }
                motion = videoData == null ? "" : videoData.path("content").asString("");
                if (!motion.matches("https://storage\\.orshot\\.com/[A-Za-z0-9_./-]+\\.mp4")) {
                    throw new IllegalArgumentException("Invalid motion asset");
                }
            }
            var result = new OrshotTemplate("orshot:" + id, metadata.path("name").asString("Orshot 디자인"),
                    header.background(), header.width(), header.height(), motion, renderHeight);
            rendered.put(id, result);
            return result;
        } catch (RuntimeException exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "ORSHOT_IMPORT_FAILED",
                    "Orshot 배경을 가져오지 못했어요. 계정의 렌더링 한도와 원본을 확인해 주세요.");
        }
    }

    /** 공고별 렌더는 공유 템플릿에 저장하거나 다른 공고와 재사용하지 않는다. */
    public OrshotTemplate renderOriginal(long id, PostingView posting) {
        requireConfigured();
        if (!ids.contains(id)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "ORSHOT_TEMPLATE_NOT_ALLOWED", "허용된 원본을 선택해 주세요.");
        }
        try {
            JsonNode metadata = originalTemplate(id);
            var content = posting.content();
            String role = content.title();
            String badge = java.util.stream.Stream.of(role, content.career())
                    .filter(value -> value != null && !value.isBlank())
                    .collect(java.util.stream.Collectors.joining(" · "));
            Map<String, Object> modifications = new LinkedHashMap<>();
            boolean hasHeadline = false;
            for (JsonNode field : metadata.path("modifications")) {
                String name = field.path("key").asString("");
                if (name.equals("hm_corner_dots") && field.path("type").asString("").equals("imageUrl")) {
                    modifications.put(name + ".opacity", 0);
                }
                if (!name.matches("(?:page[1-9][0-9]*@)?[a-zA-Z0-9_-]{1,100}")
                        || !field.path("type").asString("").equals("text")) {
                    continue;
                }
                String key = name.substring(name.indexOf('@') + 1);
                boolean headline = Set.of("headline", "title", "role_title", "hook_headline", "hm_recruitment_title",
                        "hook", "headliner", "quote", "property_address").contains(key);
                hasHeadline |= headline;
                String value = headline && !key.equals("role_title") ? role : recruitmentText(key, posting, badge);
                modifications.put(name, value == null ? "" : value);
                modifications.put(name + ".fontFamily", "Noto Sans KR");
                // 빈 문자열은 제공처에서 예시 문구를 유지할 수 있으므로 명시적으로 숨긴다.
                if (value == null || value.isBlank()) {
                    modifications.put(name + ".opacity", 0);
                }
            }
            if (!hasHeadline) {
                throw new IllegalArgumentException("No editable headline");
            }
            int sourceWidth = metadata.path("canvas_width").asInt();
            int sourceHeight = metadata.path("canvas_height").asInt();
            if (sourceWidth < 300 || sourceHeight < 300 || sourceWidth > 6000 || sourceHeight > 6000) {
                throw new IllegalArgumentException("Invalid source dimensions");
            }
            String layoutStyle = layoutStyle(metadata);
            int renderHeight = Math.max(2, 2 * (int) Math.round(sourceHeight * 300.0 / sourceWidth));
            Map<String, Object> imageResponse = layoutStyle == null
                    ? Map.of("type", "base64", "format", "jpg", "quality", 88)
                    : Map.of("type", "base64", "format", "jpg", "quality", 88,
                            "width", 600, "height", renderHeight);
            boolean multiPage = metadata.path("pages_data").size() > 1;
            if (multiPage) {
                imageResponse = new LinkedHashMap<>(imageResponse);
                imageResponse.put("includePages", List.of(1));
            }
            String image = renderAsset(id, modifications, imageResponse, Map.of());
            if (!image.matches("^data:image/(jpeg|jpg);base64,[A-Za-z0-9+/=]+$") || image.length() > 3500000) {
                throw new IllegalArgumentException("Invalid original image");
            }
            image = scaledOriginal(image);
            int motionHeight = originalHeight(image);
            boolean legacyBody = java.util.stream.StreamSupport.stream(
                    metadata.path("modifications").spliterator(), false)
                    .anyMatch(field -> field.path("key").asString("").equals("hm_intro_text"));
            Header header = layoutStyle != null ? creativeHeader(image, sourceWidth, layoutStyle)
                    : legacyBody ? legacyHeader(image) : new Header(image, 600, motionHeight);
            if (header.background().length() > 160000) {
                throw new IllegalArgumentException("Original image too large");
            }
            String motion = null;
            if (hasMotion(metadata)) {
                int videoWidth = Math.min(900, sourceWidth) / 2 * 2;
                int videoHeight = Math.max(2, 2 * (int) Math.round(sourceHeight * videoWidth / (2.0 * sourceWidth)));
                motion = renderAsset(id, modifications, layoutStyle == null
                        ? Map.of("type", "url", "format", "mp4")
                        : Map.of("type", "url", "format", "mp4", "width", videoWidth, "height", videoHeight),
                        multiPage ? Map.of("combinePages", true) : Map.of());
                if (!motion.matches("https://storage\\.orshot\\.com/[A-Za-z0-9_./-]+\\.mp4")) {
                    throw new IllegalArgumentException("Invalid original video");
                }
            }
            return new OrshotTemplate("orshot:" + id, metadata.path("name").asString("Orshot 디자인"),
                    header.background().replaceFirst("^data:image/jpg;", "data:image/jpeg;"),
                    600, header.height(), motion, motionHeight, layoutStyle);
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "ORSHOT_IMPORT_FAILED",
                    "Orshot 원본을 렌더링하지 못했어요. 계정과 원본 상태를 확인해 주세요.");
        }
    }

    private static String recruitmentText(String key, PostingView posting, String badge) {
        var content = posting.content();
        return switch (key) {
            case "company_name", "brand_name", "company", "site_name", "author_name", "event_name",
                    "hm_recruitment_company",
                    "brokerage_name", "handle", "agent_name" -> posting.companyName();
            case "role_title", "badge_text", "recap_line" -> badge;
            case "subtitle", "a_pill_text", "stat_1_value", "author_role", "s1_chip" -> content.employmentType();
            case "location_line", "city", "venue_line", "venue", "open_house_line",
                    "website", "footer_text", "stat_3_value", "s3_chip" -> content.location();
            case "salary_line", "list_price" -> content.salary();
            case "stat_2_value", "s2_chip" -> content.career();
            case "stat_4_value", "s4_chip" -> content.position();
            case "a_label", "listing_status", "category", "collection_label", "eyebrow", "live_text",
                    "hm_recruitment_label",
                    "badge", "s1_kicker", "hook_text" -> "채용 공고";
            case "b_label" -> "근무 조건";
            case "c_label", "cta_text", "end_label", "end_title", "end_headline", "tagline" -> "채용 안내";
            case "price_label" -> "급여";
            case "stat_1_label" -> "고용 형태";
            case "stat_2_label" -> "경력";
            case "stat_3_label", "open_house_label" -> "근무지";
            case "stat_4_label" -> "직급";
            case "features_title", "s3_kicker" -> "주요 업무";
            case "benefit_1", "benefit_2", "benefit_3" -> listEntry(content.benefits(), key.charAt(key.length() - 1));
            case "b1_plus", "b2_plus", "b3_plus" -> listEntry(content.benefits(), key.charAt(1)).isBlank() ? "" : "+";
            case "feature_1", "feature_2", "feature_3", "feature_4", "item_1", "item_2", "item_3",
                    "item_4", "item_5", "track_1", "track_2", "track_3", "habit_1", "habit_2", "habit_3" ->
                    listEntry(content.duties(), key.charAt(key.length() - 1));
            case "excerpt" -> content.intro();
            case "genre_tags", "hook_subtext", "offer_text", "details" -> content.jobCategory();
            case "product_1_name", "product_2_name", "product_3_name", "product_4_name" ->
                    listEntry(content.duties(), key.charAt(8));
            case "product_1_details", "product_2_details", "product_3_details", "product_4_details" ->
                    listEntry(content.qualifications(), key.charAt(8));
            case "n1", "n2", "n3", "n4", "n5" -> key.substring(1);
            default -> "";
        };
    }

    private static String listEntry(List<String> entries, char number) {
        int index = number - '1';
        return entries != null && index < entries.size() ? entries.get(index) : "";
    }

    private static String layoutStyle(JsonNode metadata) {
        Set<String> allowed = Set.of("MAGAZINE", "COLLAGE", "FEATURE", "POSTCARD", "CINEMA",
                "TYPE", "AURORA", "RIBBON", "ORBIT",
                "REEL_HIRING", "REEL_EDITORIAL", "REEL_STUDIO", "REEL_TYPE", "REEL_NEON",
                "REEL_EVENT", "REEL_BEATS", "REEL_PRODUCT", "REEL_SPACE", "REEL_LIVING");
        for (JsonNode tag : metadata.path("tags")) {
            String text = tag.asString("");
            if (text.startsWith("hiremate-layout:") && allowed.contains(text.substring(16))) {
                return text.substring(16);
            }
        }
        return null;
    }

    private static Header creativeHeader(String image, int sourceWidth, String layoutStyle) {
        try {
            BufferedImage full = ImageIO.read(new ByteArrayInputStream(
                    Base64.getDecoder().decode(image.substring(image.indexOf(',') + 1))));
            int sourceHeaderHeight = layoutStyle.startsWith("REEL_") ? 720 : 900;
            int height = Math.min(full.getHeight(), (int) Math.round(sourceHeaderHeight * 600.0 / sourceWidth));
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            ImageIO.write(full.getSubimage(0, 0, 600, height), "jpg", output);
            return new Header("data:image/jpeg;base64," + Base64.getEncoder().encodeToString(output.toByteArray()),
                    600, height);
        } catch (java.io.IOException exception) {
            throw new IllegalArgumentException("Invalid creative header", exception);
        }
    }

    static String scaledOriginal(String image) {
        try (var input = ImageIO.createImageInputStream(new ByteArrayInputStream(
                Base64.getDecoder().decode(image.substring(image.indexOf(',') + 1))))) {
            var readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new IllegalArgumentException("Invalid original image");
            }
            var reader = readers.next();
            try {
                reader.setInput(input);
                int width = reader.getWidth(0);
                int height = reader.getHeight(0);
                int scaledHeight = (int) Math.round(height * 600.0 / width);
                if (width < 30 || width > 6000 || height > 6000 || scaledHeight < 30 || scaledHeight > 3000) {
                    throw new IllegalArgumentException("Invalid original dimensions");
                }
                if (width == 600 && reader.getFormatName().equalsIgnoreCase("JPEG")) {
                    return image;
                }
                BufferedImage scaled = new BufferedImage(600, scaledHeight, BufferedImage.TYPE_INT_RGB);
                var graphics = scaled.createGraphics();
                graphics.setRenderingHint(java.awt.RenderingHints.KEY_INTERPOLATION,
                        java.awt.RenderingHints.VALUE_INTERPOLATION_BICUBIC);
                graphics.drawImage(reader.read(0), 0, 0, 600, scaledHeight, null);
                graphics.dispose();
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                ImageIO.write(scaled, "jpg", output);
                return "data:image/jpeg;base64," + Base64.getEncoder().encodeToString(output.toByteArray());
            } finally {
                reader.dispose();
            }
        } catch (java.io.IOException exception) {
            throw new IllegalArgumentException("Invalid original image", exception);
        }
    }

    /** 과거 QA 사본에 덧붙인 고정 본문을 제외하고 원본 헤더만 사용한다. */
    static Header legacyHeader(String image) {
        try {
            BufferedImage source = ImageIO.read(new ByteArrayInputStream(
                    Base64.getDecoder().decode(image.substring(image.indexOf(',') + 1))));
            int boundary = -1;
            for (int y = 150; y < source.getHeight(); y++) {
                int paper = 0;
                for (int x = 0; x < source.getWidth(); x += 6) {
                    int rgb = source.getRGB(x, y);
                    int r = (rgb >> 16) & 255;
                    int g = (rgb >> 8) & 255;
                    int b = rgb & 255;
                    if (Math.min(r, Math.min(g, b)) > 225 && Math.max(r, Math.max(g, b))
                            - Math.min(r, Math.min(g, b)) < 30) {
                        paper++;
                    }
                }
                if (paper >= 98) {
                    boundary = y;
                    break;
                }
            }
            if (boundary < 0) {
                throw new IllegalArgumentException("Legacy source body boundary not found");
            }
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            ImageIO.write(source.getSubimage(0, 0, source.getWidth(), boundary), "jpg", output);
            return new Header("data:image/jpeg;base64," + Base64.getEncoder().encodeToString(output.toByteArray()),
                    source.getWidth(), boundary);
        } catch (java.io.IOException exception) {
            throw new IllegalArgumentException("Invalid legacy source image", exception);
        }
    }

    static int originalHeight(String image) {
        try (var input = ImageIO.createImageInputStream(new ByteArrayInputStream(
                Base64.getDecoder().decode(image.substring(image.indexOf(',') + 1))))) {
            var readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new IllegalArgumentException("Invalid original image");
            }
            var reader = readers.next();
            try {
                reader.setInput(input);
                int height = reader.getHeight(0);
                if (reader.getWidth(0) != 600 || height < 30 || height > 3000) {
                    throw new IllegalArgumentException("Invalid original dimensions");
                }
                return height;
            } finally {
                reader.dispose();
            }
        } catch (java.io.IOException exception) {
            throw new IllegalArgumentException("Invalid original image", exception);
        }
    }

    private JsonNode originalTemplate(long id) {
        try {
            return template(id);
        } catch (WebClientResponseException.Forbidden | WebClientResponseException.NotFound exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "ORSHOT_ORIGINAL_UNAVAILABLE",
                    "연결된 Orshot 계정에서 이 원본을 열 수 없어요. 원본이 있는 워크스페이스를 확인해 주세요.");
        }
    }

    private String renderAsset(long id, Map<String, Object> modifications, Map<String, Object> response,
            Map<String, Object> videoOptions) {
        Map<String, Object> request = new LinkedHashMap<>(Map.of(
                "templateId", id, "lang", "ko", "modifications", modifications, "response", response));
        if (!videoOptions.isEmpty()) {
            request.put("videoOptions", videoOptions);
        }
        JsonNode result = http.post().uri("/v1/studio/render").headers(headers -> headers.setBearerAuth(key))
                .bodyValue(request).retrieve().bodyToMono(JsonNode.class).block(Duration.ofSeconds(90));
        JsonNode data = result == null ? null : result.path("data");
        if (data != null && data.isArray()) {
            if (data.size() != 1) {
                throw new IllegalArgumentException("Multi-page original is unsupported");
            }
            data = data.path(0);
        }
        return data == null ? "" : data.path("content").asString("");
    }

    private void requireConfigured() {
        if (key.isEmpty() || ids.isEmpty()) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "ORSHOT_NOT_CONFIGURED",
                    "Orshot 키와 사용할 공용 템플릿 설정이 필요해요.");
        }
    }

    private JsonNode template(long id) {
        return http.get().uri("/v1/studio/templates/{id}", id).headers(headers -> headers.setBearerAuth(key))
                .retrieve().bodyToMono(JsonNode.class).block(Duration.ofSeconds(20));
    }

    private Optional<JsonNode> accessibleTemplate(long id) {
        try {
            return Optional.ofNullable(template(id));
        } catch (WebClientResponseException.Forbidden | WebClientResponseException.NotFound exception) {
            return Optional.empty();
        }
    }

    private static int score(JsonNode node, String query) {
        String description = (node.path("name").asString("") + " " + node.path("description").asString("")
                + " " + node.path("tags").toString())
                .toLowerCase(Locale.ROOT);
        return (int) java.util.Arrays.stream(query.toLowerCase(Locale.ROOT).split("\\s+"))
                .filter(word -> word.length() > 2 && description.contains(word)).count();
    }

    static Header compactHeader(String data) {
        if (!data.matches("^data:image/(jpeg|jpg);base64,[A-Za-z0-9+/=]+$") || data.length() > 3500000) {
            throw new IllegalArgumentException("Unexpected image response");
        }
        try (var input = ImageIO.createImageInputStream(new ByteArrayInputStream(
                Base64.getDecoder().decode(data.substring(data.indexOf(',') + 1))))) {
            var readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw new IllegalArgumentException("Invalid image");
            }
            var reader = readers.next();
            try {
                reader.setInput(input);
                if (reader.getWidth(0) > 5000 || reader.getHeight(0) > 6000) {
                    throw new IllegalArgumentException("Image too large");
                }
                BufferedImage source = reader.read(0);
                int crop = Math.max(1, (int) (source.getHeight() * 0.6));
                int height = Math.clamp(Math.round(crop * 600.0 / source.getWidth()), 260, 480);
                BufferedImage scaled = new BufferedImage(600, height, BufferedImage.TYPE_INT_RGB);
                var graphics = scaled.createGraphics();
                graphics.drawImage(source, 0, 0, 600, height, 0, 0, source.getWidth(), crop, null);
                graphics.dispose();
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                ImageIO.write(scaled, "jpg", output);
                if (output.size() > 110000) {
                    throw new IllegalArgumentException("Header too large");
                }
                return new Header("data:image/jpeg;base64," + Base64.getEncoder().encodeToString(output.toByteArray()),
                        600, height);
            } finally {
                reader.dispose();
            }
        } catch (java.io.IOException exception) {
            throw new IllegalArgumentException("Invalid header", exception);
        }
    }

    record Header(String background, int width, int height) {
    }

    public record OrshotTemplate(String id, String name, String background, int width, int height,
            @Schema(nullable = true) String motionUrl, int motionHeight,
            @Schema(nullable = true) String layoutStyle) {
        public OrshotTemplate(String id, String name, String background, int width, int height,
                String motionUrl, int motionHeight) {
            this(id, name, background, width, height, motionUrl, motionHeight, null);
        }

        public OrshotTemplate(String id, String name, String background, int width, int height) {
            this(id, name, background, width, height, null, 0, null);
        }
    }
}
