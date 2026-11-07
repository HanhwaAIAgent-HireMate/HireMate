package com.hiremate.posting;

import com.hiremate.global.ApiException;
import com.hiremate.posting.PosterProposal.FreeTemplate;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import tools.jackson.databind.JsonNode;

/** 공개 갤러리와 명시적으로 허용한 공용 테마만 읽는다. 기업 공고와 키를 AI에 보내지 않는다. */
@Service
public class TemplatedLibrary {
    private final WebClient http;
    private final String key;
    private final List<String> sharedIds;

    public TemplatedLibrary(WebClient.Builder builder, @Value("${TEMPLATED_API_KEY:}") String key,
            @Value("${TEMPLATED_TEMPLATE_IDS:}") String ids) {
        this.http = builder.baseUrl("https://api.templated.io")
                .codecs(config -> config.defaultCodecs().maxInMemorySize(8 * 1024 * 1024)).build();
        this.key = key.strip();
        this.sharedIds = java.util.Arrays.stream(ids.split(",")).map(String::strip)
                .filter(id -> id.matches("[a-fA-F0-9-]{36}")).limit(3).toList();
    }

    public List<FreeTemplate> search(String query) {
        return search(query, Set.of());
    }

    public List<FreeTemplate> search(String query, Set<String> excluded) {
        return search(query, excluded, false);
    }

    public List<FreeTemplate> search(String query, Set<String> excluded, boolean includeRelated) {
        if (key.isEmpty()) {
            throw new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "TEMPLATED_NOT_CONFIGURED",
                    "외부 템플릿 서비스 연결 설정이 필요해요.");
        }
        try {
            List<JsonNode> rows = gallery(query);
            // 계정 전체 라이브러리를 조회하지 않는다. 관리자가 승인한 공용 디자인만 포함한다.
            for (String id : sharedIds) {
                JsonNode shared = get("/v1/template/" + id + "?includeLayers=true");
                if (shared != null && shared.isObject()) {
                    rows.add(shared);
                }
            }
            List<JsonNode> eligible = rows.stream()
                    .filter(row -> !excluded.contains("templated:" + row.path("id").asString("")))
                    .toList();
            List<FreeTemplate> matched = candidates(eligible, query);
            if (includeRelated && matched.isEmpty()) {
                List<JsonNode> related = gallery("recruitment hiring").stream()
                        .filter(row -> !excluded.contains("templated:" + row.path("id").asString("")))
                        .toList();
                return candidates(related, "recruitment hiring vacancy careers");
            }
            return matched;
        } catch (ApiException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "TEMPLATED_UNAVAILABLE",
                    "외부 템플릿을 조회하지 못했어요. 연결 설정을 확인하고 다시 요청해 주세요.");
        }
    }

    private List<JsonNode> gallery(String query) {
        List<JsonNode> rows = new ArrayList<>();
        for (String word : java.util.Arrays.stream(query.split("\\s+"))
                .filter(word -> word.length() > 2).distinct().limit(4).toList()) {
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
        int score = 0;
        for (String word : query.toLowerCase(Locale.ROOT).split("\\s+")) {
            if (word.length() > 2 && words.contains(word)) {
                score++;
            }
        }
        return score;
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
        double x = dimension(layer, "x");
        double y = dimension(layer, "y");
        double width = dimension(layer, "width");
        double height = dimension(layer, "height");
        String type = layer.path("type").asString("");
        svg.append("<g data-layer=\"").append(escape(layer.path("layer").asString("element")))
                .append("\" data-kind=\"").append(type.equals("text") ? "TEXT" : "SHAPE")
                .append("\" data-x=\"").append(x).append("\" data-y=\"").append(y)
                .append("\" data-width=\"").append(width).append("\" data-height=\"").append(height)
                .append("\">");
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
            String text = layer.path("text").asString("").replaceAll("<[^>]*>", " ");
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

    private static String color(String value, String fallback) {
        return value.matches("#[a-fA-F0-9]{6}|#[a-fA-F0-9]{3}|rgba?\\([0-9., ]+\\)") ? value : fallback;
    }

    private static String escape(String value) {
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\"", "&quot;").replace("'", "&apos;");
    }
}
