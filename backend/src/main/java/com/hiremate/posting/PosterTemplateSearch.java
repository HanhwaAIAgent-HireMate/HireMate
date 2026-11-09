package com.hiremate.posting;

import com.hiremate.company.CanvaConnectionService.CanvaDesign;
import com.hiremate.posting.PosterProposal.FreeTemplate;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.net.URI;
import java.time.Duration;
import java.util.ArrayList;
import java.util.BitSet;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import javax.imageio.ImageIO;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

/** 두 제공처의 후보를 번갈아 보존하고 동일 원본과 시각적으로 같은 복사본을 제거한다. */
@Service
public class PosterTemplateSearch {
    private final WebClient http;

    public PosterTemplateSearch(WebClient.Builder builder) {
        http = builder.codecs(config -> config.defaultCodecs().maxInMemorySize(1024 * 1024)).build();
    }

    /** 검색 풀의 정렬 힌트다. 두 글자 약어는 다른 단어의 일부와 일치시키지 않는다. */
    static int keywordScore(String description, String query) {
        String text = description.toLowerCase(Locale.ROOT);
        Set<String> tokens = new HashSet<>(List.of(text.split("[^\\p{L}\\p{N}]+")));
        return (int) java.util.Arrays.stream(query.toLowerCase(Locale.ROOT).split("\\s+"))
                .filter(word -> word.length() >= 2).distinct()
                .filter(word -> word.length() == 2 ? tokens.contains(word) : text.contains(word)).count();
    }

    public Result combine(List<FreeTemplate> templates, List<CanvaDesign> designs) {
        return combine(templates, designs, Set.of());
    }

    public Result combine(List<FreeTemplate> templates, List<CanvaDesign> designs, Set<String> excluded) {
        List<FreeTemplate> keptTemplates = new ArrayList<>();
        List<CanvaDesign> keptDesigns = new ArrayList<>();
        Set<String> ids = new HashSet<>(excluded);
        Set<String> urls = new HashSet<>();
        List<Fingerprint> images = new ArrayList<>();
        for (int i = 0; i < Math.max(templates.size(), designs.size()); i++) {
            if (i < templates.size()) {
                FreeTemplate item = templates.get(i);
                if (unique(item.id(), item.thumbnailUrl(), ids, urls, images)) {
                    keptTemplates.add(item);
                }
            }
            if (keptTemplates.size() + keptDesigns.size() >= 3) {
                break;
            }
            if (i < designs.size()) {
                CanvaDesign item = designs.get(i);
                if (unique("canva:" + item.id(), item.thumbnailUrl(), ids, urls, images)) {
                    keptDesigns.add(item);
                }
            }
            if (keptTemplates.size() + keptDesigns.size() >= 3) {
                break;
            }
        }
        return new Result(List.copyOf(keptTemplates), List.copyOf(keptDesigns));
    }

    private boolean unique(String id, String url, Set<String> ids, Set<String> urls, List<Fingerprint> images) {
        if (!ids.add(id)) {
            return false;
        }
        if (url != null && !url.isBlank() && !urls.add(url.split("\\?", 2)[0])) {
            return false;
        }
        Fingerprint fingerprint = download(url);
        if (fingerprint != null) {
            if (images.stream().anyMatch(image -> image.similar(fingerprint))) {
                return false;
            }
            images.add(fingerprint);
        }
        return true;
    }

    private Fingerprint download(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            URI uri = URI.create(value);
            String host = uri.getHost();
            if (!"https".equals(uri.getScheme()) || uri.getUserInfo() != null || uri.getPort() != -1
                    || host == null || !(host.equals("templated-assets.s3.amazonaws.com")
                    || host.equals("media.canva.com") || host.endsWith(".canva.com")
                    || host.equals("storage.orshot.com"))) {
                return null;
            }
            byte[] bytes = http.get().uri(uri).retrieve().bodyToMono(byte[].class).block(Duration.ofSeconds(6));
            if (bytes == null) {
                return null;
            }
            try (var stream = ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
                var readers = ImageIO.getImageReaders(stream);
                if (!readers.hasNext()) {
                    return null;
                }
                var reader = readers.next();
                try {
                    reader.setInput(stream);
                    if (reader.getWidth(0) > 8192 || reader.getHeight(0) > 8192) {
                        return null;
                    }
                    return fingerprint(reader.read(0));
                } finally {
                    reader.dispose();
                }
            }
        } catch (Exception exception) {
            // 미리보기를 읽지 못한 후보를 서로 같다고 추정하지 않는다.
            return null;
        }
    }

    static Fingerprint fingerprint(BufferedImage source) {
        BufferedImage sample = new BufferedImage(17, 16, BufferedImage.TYPE_INT_RGB);
        var graphics = sample.createGraphics();
        graphics.drawImage(source, 0, 0, 17, 16, null);
        graphics.dispose();
        BitSet hash = new BitSet(256);
        long total = 0;
        for (int y = 0; y < 16; y++) {
            for (int x = 0; x < 16; x++) {
                int pixel = sample.getRGB(x, y);
                int next = sample.getRGB(x + 1, y);
                int light = ((pixel >> 16) & 255) + ((pixel >> 8) & 255) + (pixel & 255);
                int right = ((next >> 16) & 255) + ((next >> 8) & 255) + (next & 255);
                hash.set(y * 16 + x, light > right);
                total += light;
            }
        }
        return new Fingerprint(hash, (int) (total / 768), source.getWidth() / (double) source.getHeight());
    }

    record Fingerprint(BitSet hash, int brightness, double ratio) {
        boolean similar(Fingerprint other) {
            BitSet difference = (BitSet) hash.clone();
            difference.xor(other.hash);
            return difference.cardinality() <= 5 && Math.abs(brightness - other.brightness) <= 8
                    && Math.abs(ratio - other.ratio) <= 0.025;
        }
    }

    public record Result(List<FreeTemplate> templates, List<CanvaDesign> designs) {
    }
}
