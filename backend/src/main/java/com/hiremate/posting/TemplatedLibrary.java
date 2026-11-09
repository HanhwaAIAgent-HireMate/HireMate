package com.hiremate.posting;

import com.hiremate.global.ApiException;
import com.hiremate.posting.PosterProposal.FreeTemplate;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import javax.imageio.ImageIO;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.BodyExtractors;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import tools.jackson.databind.JsonNode;

/** 공개 갤러리와 명시적으로 허용한 공용 테마만 읽는다. 기업 공고와 키를 AI에 보내지 않는다. */
@Service
public class TemplatedLibrary {
    private static final String RECRUITMENT = "recruitment hiring vacancy careers";
    private static final String BANNER_TOPICS = "business corporate technology office finance education event";
    private static final Set<String> VISUAL_CATEGORIES = Set.of(
            "Open Graph", "Social Media", "YouTube Thumbnail", "Marketing");
    private static final String PUBLIC_ASSET =
            "https://templated-assets\\.s3\\.amazonaws\\.com/(?:public/pixabay-images/[0-9]+|upload/[a-fA-F0-9-]{36})";
    private final WebClient http;
    private final String key;
    private final List<String> sharedIds;
    private final Map<String, String> registrations = new ConcurrentHashMap<>();

    public TemplatedLibrary(WebClient.Builder builder, @Value("${TEMPLATED_API_KEY:}") String key,
            @Value("${TEMPLATED_TEMPLATE_IDS:}") String ids) {
        this.http = builder.baseUrl("https://api.templated.io")
                .codecs(config -> config.defaultCodecs().maxInMemorySize(8 * 1024 * 1024)).build();
        this.key = key.strip();
        this.sharedIds = java.util.Arrays.stream(ids.split(",")).map(String::strip)
                .filter(id -> id.matches("[a-fA-F0-9-]{36}")).limit(3).toList();
    }

    public List<FreeTemplate> searchGallery(String query, Set<String> excluded) {
        return search(query, excluded, true, false);
    }

    public List<FreeTemplate> search(String query) {
        return search(query, Set.of());
    }

    public List<FreeTemplate> search(String query, Set<String> excluded) {
        return search(query, excluded, false);
    }

    public List<FreeTemplate> search(String query, Set<String> excluded, boolean includeRelated) {
        return search(query, excluded, includeRelated, true);
    }

    private List<FreeTemplate> search(String query, Set<String> excluded, boolean includeRelated,
            boolean includeShared) {
        if (key.isEmpty()) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "TEMPLATED_NOT_CONFIGURED",
                    "외부 템플릿 서비스 연결 설정이 필요해요.");
        }
        try {
            List<JsonNode> rows = gallery(query);
            // 계정 전체 라이브러리를 조회하지 않는다. 관리자가 승인한 공용 디자인만 포함한다.
            for (String id : includeShared ? sharedIds : List.<String>of()) {
                JsonNode shared = get("/v1/template/" + id + "?includeLayers=true");
                if (shared != null && shared.isObject()) {
                    rows.add(shared);
                }
            }
            List<JsonNode> eligible = rows.stream()
                    .filter(row -> !excluded.contains("templated:" + row.path("id").asString("")))
                    .toList();
            List<FreeTemplate> matched = candidates(includeShared ? eligible : eligible.stream()
                    .filter(row -> score(row, RECRUITMENT) > 0).toList(), query);
            if (includeRelated && matched.isEmpty()) {
                List<JsonNode> related = gallery("recruitment hiring").stream()
                        .filter(row -> !excluded.contains("templated:" + row.path("id").asString("")))
                        .toList();
                List<FreeTemplate> relatedMatches = candidates(related, RECRUITMENT);
                if (!relatedMatches.isEmpty() || includeShared) {
                    return relatedMatches;
                }
                List<FreeTemplate> banners = publicBanners(query, excluded);
                if (!banners.isEmpty()) {
                    return banners;
                }
                List<JsonNode> approved = new ArrayList<>();
                for (String id : sharedIds) {
                    if (!excluded.contains("templated:" + id)) {
                        JsonNode template = get("/v1/template/" + id + "?includeLayers=true");
                        if (template != null && template.isObject()) {
                            approved.add(template);
                        }
                    }
                }
                return candidates(approved, RECRUITMENT);
            }
            return matched;
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "TEMPLATED_UNAVAILABLE",
                    "외부 템플릿을 조회하지 못했어요. 연결 설정을 확인하고 다시 요청해 주세요.");
        }
    }

    private List<FreeTemplate> publicBanners(String query, Set<String> excluded) {
        JsonNode gallery = get("/v1/templates/gallery?limit=100&includeLayers=true");
        if (gallery == null || !gallery.isArray()) {
            return List.of();
        }
        List<JsonNode> rows = new ArrayList<>();
        gallery.forEach(rows::add);
        List<FreeTemplate> results = new ArrayList<>();
        Set<String> photos = new HashSet<>();
        for (JsonNode row : rows.stream()
                .filter(item -> score(item, BANNER_TOPICS) > 0
                        || (VISUAL_CATEGORIES.contains(item.path("categoryName").asString(""))
                        && score(item, query) > 0)
                        || ("Open Graph".equals(item.path("categoryName").asString(""))
                        && PosterTemplateSearch.keywordScore("frontend web interface", query) > 0))
                .sorted(Comparator.comparingInt((JsonNode item) -> score(item, query)).reversed()).toList()) {
            String id = "templated:" + row.path("id").asString("");
            String name = row.path("name").asString("").strip();
            if (!id.matches("templated:[a-fA-F0-9-]{36}") || excluded.contains(id) || name.isEmpty()) {
                continue;
            }
            JsonNode layer = bannerPhoto(row);
            if (layer == null) {
                continue;
            }
            String photo = layer.path("image_url").asString("");
            if (photo.isEmpty() || !photos.add(photo)) {
                continue;
            }
            String jpeg = loadBannerPhoto(photo);
            if (!jpeg.isEmpty()) {
                String svg = bannerPreview(row, layer, jpeg);
                if (svg.length() <= 100000) {
                    results.add(new FreeTemplate(id, name.substring(0, Math.min(name.length(), 100)),
                            "https://templated.io/templates/", "Templated 테마", svg, ""));
                }
            }
            if (results.size() == 3 || photos.size() == 5) {
                break;
            }
        }
        return List.copyOf(results);
    }

    private static JsonNode bannerPhoto(JsonNode row) {
        int width = row.path("width").asInt();
        int height = row.path("height").asInt();
        if (width < 300 || width > 5000 || height < 300 || height > 5000
                || row.path("layers").size() > 150) {
            return null;
        }
        for (JsonNode layer : row.path("layers")) {
            String url = layer.path("image_url").asString("");
            if (layer.path("type").asString("").equals("image") && !layer.path("hide").asBoolean(false)
                    && dimension(layer, "width") >= width * 0.65
                    && dimension(layer, "height") >= height * 0.45 && url.matches(PUBLIC_ASSET)) {
                return layer;
            }
        }
        return null;
    }

    private static String bannerPreview(JsonNode row, JsonNode photo, String jpeg) {
        int width = row.path("width").asInt();
        int height = row.path("height").asInt();
        String paper = color(row.path("background").asString(""), "#f7f5ef");
        StringBuilder svg = new StringBuilder("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"")
                .append(width).append("\" height=\"").append(height).append("\" data-templated-artwork=\"true\">")
                .append("<rect width=\"").append(width).append("\" height=\"").append(height)
                .append("\" fill=\"").append(paper).append("\"/>");
        for (JsonNode layer : row.path("layers")) {
            if (layer.path("hide").asBoolean(false)) {
                continue;
            }
            if (layer == photo) {
                svg.append("<g data-templated-photo=\"").append(jpeg).append("\" data-x=\"")
                        .append(coordinate(layer, "x")).append("\" data-y=\"").append(coordinate(layer, "y"))
                        .append("\" data-width=\"").append(dimension(layer, "width"))
                        .append("\" data-height=\"").append(dimension(layer, "height")).append("\"/>");
            } else if (Set.of("shape", "text").contains(layer.path("type").asString(""))) {
                appendLayer(svg, layer, false);
            }
        }
        return svg.append("</svg>").toString();
    }

    private String loadBannerPhoto(String url) {
        try {
            // 공개 이미지 요청에는 Templated 키를 붙이지 않는다.
            // 일부 공개 이미지의 Content-Type은 jpg 또는 png라서 MIME 파싱 없이 원본을 읽는다.
            byte[] bytes = http.get().uri(URI.create(url)).exchangeToMono(response -> {
                if (!response.statusCode().is2xxSuccessful()) {
                    return response.releaseBody().then(reactor.core.publisher.Mono.empty());
                }
                return DataBufferUtils.join(response.body(BodyExtractors.toDataBuffers()), 8 * 1024 * 1024)
                        .map(buffer -> {
                            try {
                                byte[] body = new byte[buffer.readableByteCount()];
                                buffer.read(body);
                                return body;
                            } finally {
                                DataBufferUtils.release(buffer);
                            }
                        });
            })
                    .block(Duration.ofSeconds(5));
            if (bytes == null) {
                return "";
            }
            try (var stream = ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
                var readers = ImageIO.getImageReaders(stream);
                if (!readers.hasNext()) {
                    return "";
                }
                var reader = readers.next();
                try {
                    reader.setInput(stream);
                    if (reader.getWidth(0) > 8192 || reader.getHeight(0) > 8192) {
                        return "";
                    }
                    return bannerJpeg(reader.read(0));
                } finally {
                    reader.dispose();
                }
            }
        } catch (Exception exception) {
            return "";
        }
    }

    private static String bannerJpeg(BufferedImage image) throws java.io.IOException {
        double scale = Math.min(1, 650d / Math.max(image.getWidth(), image.getHeight()));
        int width = Math.max(1, (int) Math.round(image.getWidth() * scale));
        int height = Math.max(1, (int) Math.round(image.getHeight() * scale));
        BufferedImage banner = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        var graphics = banner.createGraphics();
        try {
            graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            graphics.drawImage(image, 0, 0, width, height, java.awt.Color.WHITE, null);
        } finally {
            graphics.dispose();
        }
        var output = new ByteArrayOutputStream();
        ImageIO.write(banner, "jpg", output);
        return output.size() <= 70000 ? Base64.getEncoder().encodeToString(output.toByteArray()) : "";
    }

    private List<JsonNode> gallery(String query) {
        List<JsonNode> rows = new ArrayList<>();
        for (String word : java.util.Arrays.stream(query.split("\\s+"))
                .filter(word -> word.length() >= 2).distinct().limit(4).toList()) {
            JsonNode page = get("/v1/templates/gallery?limit=100&includeLayers=true&query="
                    + URLEncoder.encode(word, StandardCharsets.UTF_8));
            if (page != null && page.isArray()) {
                page.forEach(rows::add);
            }
        }
        return rows;
    }

    private JsonNode get(String path) {
        return http.get().uri(path).headers(headers -> headers.setBearerAuth(key)).retrieve()
                .bodyToMono(JsonNode.class).block(Duration.ofSeconds(30));
    }

    public RegisteredTemplate register(UUID companyId, String sourceId, String name, String svg, int height) {
        if (key.isEmpty()) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "TEMPLATED_NOT_CONFIGURED",
                    "Templated API 키를 설정해 주세요.");
        }
        validateGeneratedSvg(svg, height);
        String requestKey = companyId + ":" + sourceId + ":"
                + UUID.nameUUIDFromBytes(svg.getBytes(StandardCharsets.UTF_8));
        try {
            String id = registrations.computeIfAbsent(requestKey, ignored -> {
                JsonNode created = http.post().uri("/v1/template")
                        .headers(headers -> headers.setBearerAuth(key))
                        .bodyValue(Map.of("name", name, "width", 600, "height", height,
                                "layers", List.of(Map.of("layer", "poster", "type", "shape",
                                        "x", 0, "y", 0, "width", 600, "height", height, "html", svg))))
                        .retrieve().bodyToMono(JsonNode.class).block(Duration.ofSeconds(45));
                String result = created == null ? "" : created.path("id").asString("");
                if (!result.matches("[a-fA-F0-9-]{36}")) {
                    throw new IllegalArgumentException("Invalid created template ID");
                }
                return result;
            });
            JsonNode saved = get("/v1/template/" + id + "?includeLayers=true");
            if (saved == null || !id.equals(saved.path("id").asString(""))) {
                throw new IllegalArgumentException("Registered template was not retrieved");
            }
            return new RegisteredTemplate("templated:" + id, saved.path("name").asString(name));
        } catch (WebClientResponseException.Forbidden exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "TEMPLATED_TEMPLATE_LIMIT",
                    "Templated 등록 권한 또는 저장 가능한 템플릿 개수를 확인해 주세요.");
        } catch (RuntimeException exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "TEMPLATED_REGISTRATION_FAILED",
                    "Templated에 새 양식을 등록하거나 다시 불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
        }
    }

    public record RegisteredTemplate(String id, String name) {
    }

    private static void validateGeneratedSvg(String svg, int height) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
            factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
            factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
            var root = factory.newDocumentBuilder().parse(new org.xml.sax.InputSource(
                    new java.io.StringReader(svg))).getDocumentElement();
            if (!root.getLocalName().equals("svg") || height < 300 || height > 5000
                    || !root.getAttribute("viewBox").equals("0 0 600 " + height)) {
                throw new IllegalArgumentException("Invalid generated SVG dimensions");
            }
            Set<String> allowed = Set.of("svg", "g", "defs", "clipPath", "rect", "circle", "ellipse",
                    "line", "polygon", "polyline", "path", "text", "tspan", "image",
                    "linearGradient", "radialGradient", "stop", "pattern", "desc", "title");
            var nodes = root.getElementsByTagName("*");
            if (nodes.getLength() > 15000) {
                throw new IllegalArgumentException("Too many SVG elements");
            }
            for (int index = -1; index < nodes.getLength(); index++) {
                var node = index < 0 ? root : (org.w3c.dom.Element) nodes.item(index);
                if (!allowed.contains(node.getLocalName())) {
                    throw new IllegalArgumentException("Unsupported SVG element");
                }
                var attributes = node.getAttributes();
                for (int at = 0; at < attributes.getLength(); at++) {
                    var attribute = attributes.item(at);
                    String value = attribute.getNodeValue();
                    String attributeName = attribute.getNodeName().toLowerCase(Locale.ROOT);
                    if (attributeName.startsWith("on") || value.contains("@import")
                            || value.toLowerCase(Locale.ROOT).contains("javascript:")
                            || value.matches("(?is).*url\\(\\s*['\"]?(?!#).*")
                            || attributeName.endsWith("href") && !value.matches(
                                    "data:image/(png|jpeg);base64,[A-Za-z0-9+/=]+")) {
                        throw new IllegalArgumentException("External SVG reference");
                    }
                }
            }
        } catch (Exception exception) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_TEMPLATED_DESIGN",
                    "등록할 포스터 양식을 확인하지 못했어요.");
        }
    }

    static List<FreeTemplate> candidates(List<JsonNode> rows, String query) {
        Set<String> ids = new HashSet<>();
        Set<String> names = new HashSet<>();
        Set<String> layouts = new HashSet<>();
        List<FreeTemplate> result = new ArrayList<>();
        for (JsonNode row : rows.stream().sorted(Comparator.comparingInt(
                (JsonNode item) -> score(item, query)).reversed()).toList()) {
            String id = row.path("id").asString("");
            String name = row.path("name").asString("").strip();
            if (!id.matches("[a-fA-F0-9-]{36}") || name.isEmpty() || score(row, query) == 0
                    || !ids.add(id) || !names.add(name.toLowerCase(Locale.ROOT).replaceAll("\\s+", ""))) {
                continue;
            }
            String svg = preview(row);
            if (svg != null && layouts.add(layoutKey(row))) {
                result.add(new FreeTemplate("templated:" + id, name.substring(0, Math.min(name.length(), 100)),
                        "https://templated.io/templates/", "Templated 테마", svg,
                        row.path("thumbnail").asString("")));
            }
            if (result.size() == 3) {
                break;
            }
        }
        return List.copyOf(result);
    }

    /** 문구와 색만 다른 복제본은 같은 후보로 취급한다. */
    private static String layoutKey(JsonNode row) {
        StringBuilder key = new StringBuilder().append(row.path("width").asInt())
                .append(':').append(row.path("height").asInt());
        for (JsonNode layer : row.path("layers")) {
            if (!layer.path("hide").asBoolean(false)) {
                key.append('|').append(layer.path("type").asString(""));
                for (String field : List.of("x", "y", "width", "height")) {
                    key.append(':').append(Math.round(dimension(layer, field) / 8));
                }
            }
        }
        return key.toString();
    }

    private static int score(JsonNode row, String query) {
        String words = (row.path("name").asString("") + " " + row.path("description").asString(""))
                .toLowerCase(Locale.ROOT);
        return PosterTemplateSearch.keywordScore(words, query);
    }

    /** 임의 HTML, 스크립트, 이미지 URL은 복사하지 않고 지원하는 벡터·텍스트만 재구성한다. */
    static String preview(JsonNode row) {
        int width = row.path("width").asInt();
        int height = row.path("height").asInt();
        JsonNode layers = row.path("layers");
        String category = row.path("categoryName").asString("");
        if (Set.of("Resume", "Receipt", "Invoice", "Certificate", "Shipping Label").contains(category)) {
            return null;
        }
        if (width < 300 || width > 5000 || height < width || height > 5000
                || !layers.isArray() || layers.size() > 150 || layers.isEmpty()) {
            return null;
        }
        for (JsonNode layer : layers) {
            if (Set.of("image", "video").contains(layer.path("type").asString(""))) {
                return null;
            }
        }
        double bodyTop = height * 0.3;
        for (JsonNode layer : layers) {
            if (layer.path("type").asString("").equals("shape")
                    && layer.path("y").asDouble() == 0 && layer.path("width").asDouble() >= width * 0.9
                    && layer.path("height").asDouble() >= height * 0.15
                    && layer.path("height").asDouble() <= height * 0.6) {
                bodyTop = layer.path("height").asDouble();
            }
        }
        String paper = color(row.path("background").asString(""), "#f7f5ef");
        StringBuilder svg = new StringBuilder("<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"")
                .append(width).append("\" height=\"").append(height).append("\" data-body-top=\"")
                .append(bodyTop).append("\"><rect width=\"").append(width).append("\" height=\"")
                .append(height).append("\" fill=\"").append(paper).append("\"/>");
        for (JsonNode layer : layers) {
            if (!layer.path("hide").asBoolean(false)) {
                appendLayer(svg, layer);
            }
        }
        svg.append("</svg>");
        return svg.length() <= 100000 ? svg.toString() : null;
    }

    private static void appendLayer(StringBuilder svg, JsonNode layer) {
        appendLayer(svg, layer, true);
    }

    private static void appendLayer(StringBuilder svg, JsonNode layer, boolean copyText) {
        double x = coordinate(layer, "x");
        double y = coordinate(layer, "y");
        double width = dimension(layer, "width");
        double height = dimension(layer, "height");
        String type = layer.path("type").asString("");
        svg.append("<g data-layer=\"").append(escape(layer.path("layer").asString("element")))
                .append("\" data-kind=\"").append(type.equals("text") ? "TEXT" : "SHAPE")
                .append("\" data-x=\"").append(x).append("\" data-y=\"").append(y)
                .append("\" data-width=\"").append(width).append("\" data-height=\"").append(height)
                .append("\" opacity=\"").append(layerOpacity(layer)).append("\">");
        if (type.equals("shape")) {
            String shape = safeShape(layer.path("html").asString(""));
            if (!shape.isEmpty()) {
                svg.append("<g transform=\"translate(").append(x).append(" ").append(y).append(")\">")
                        .append(shape).append("</g></g>");
                return;
            }
            svg.append("<rect x=\"").append(x).append("\" y=\"").append(y)
                    .append("\" width=\"").append(width).append("\" height=\"").append(height)
                    .append("\" fill=\"").append(color(layer.path("fill").asString(""), "#082858"))
                    .append("\"/>");
        } else if (type.equals("text")) {
            String size = layer.path("font_size").asString("24px").replace("px", "");
            if (!size.matches("[0-9]{1,3}(\\.[0-9]+)?")) {
                size = "24";
            }
            double fontSize = Double.parseDouble(size);
            String text = copyText ? layer.path("text").asString("").replaceAll("<[^>]*>", " ") : "";
            svg.append("<text x=\"").append(x).append("\" y=\"").append(y + fontSize)
                    .append("\" font-family=\"Noto Sans KR, sans-serif\" font-size=\"").append(size)
                    .append("\" font-weight=\"").append("bold".equals(layer.path("font_weight").asString(""))
                            ? "bold" : "normal")
                    .append("\" fill=\"").append(color(layer.path("color").asString(""), "#24313e"))
                    .append("\">").append(escape(text)).append("</text>");
        }
        svg.append("</g>");
    }

    private static String safeShape(String html) {
        StringBuilder result = new StringBuilder();
        var tags = java.util.regex.Pattern.compile("<(rect|circle|ellipse|line|polygon|polyline|path)\\b([^>]*)>")
                .matcher(html);
        Set<String> allowed = Set.of("x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "x1", "x2",
                "y1", "y2", "points", "d", "fill", "stroke", "stroke-width", "opacity", "fill-opacity");
        while (tags.find()) {
            result.append("<").append(tags.group(1));
            var attrs = java.util.regex.Pattern.compile("([a-z-]+)\\s*=\\s*['\"]([^'\"]*)['\"]")
                    .matcher(tags.group(2));
            while (attrs.find()) {
                String name = attrs.group(1);
                String value = attrs.group(2);
                boolean valid = name.equals("fill") || name.equals("stroke")
                        ? !color(value, "").isEmpty() || value.equals("none")
                        : value.matches("[0-9., +%MmLlHhVvCcSsQqTtAaZzEe-]+");
                if (allowed.contains(name) && valid) {
                    result.append(" ").append(name).append("=\"").append(escape(value)).append("\"");
                }
            }
            result.append("/>");
        }
        return result.toString();
    }

    private static double dimension(JsonNode layer, String key) {
        double value = layer.path(key).asDouble();
        return Double.isFinite(value) ? Math.max(0, Math.min(10000, value)) : 0;
    }

    private static double coordinate(JsonNode layer, String key) {
        double value = layer.path(key).asDouble();
        return Double.isFinite(value) ? Math.clamp(value, -10000, 10000) : 0;
    }

    private static double layerOpacity(JsonNode layer) {
        double opacity = layer.path("opacity").asDouble(1);
        return Double.isFinite(opacity) && opacity >= 0 && opacity <= 1 ? opacity : 1;
    }

    private static String color(String value, String fallback) {
        return value.matches("#[a-fA-F0-9]{6}|#[a-fA-F0-9]{3}|rgba?\\([0-9., ]+\\)") ? value : fallback;
    }

    private static String escape(String value) {
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\"", "&quot;").replace("'", "&apos;");
    }
}
