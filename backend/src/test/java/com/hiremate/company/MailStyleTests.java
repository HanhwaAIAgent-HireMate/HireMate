package com.hiremate.company;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import com.hiremate.TestFixtures;
import com.hiremate.TestMailConfiguration;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Random;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;

class MailStyleTests extends IntegrationTest {

    private static final String BASE = "/api/companies/me/mail-style";
    private static final byte[] PNG = image(80, 40, "png");

    @Autowired
    private TestMailConfiguration.RecordingMailClient mail;

    @Test
    @DisplayName("큰 로고와 배너는 메일 크기에 맞춰 비율대로 줄여 저장하고, 형식만 흉내 낸 파일은 거절한다")
    void largeImagesAreShrunk() throws Exception {
        TestApi hr = newHr();
        byte[] logo = image(1600, 800, "png");
        byte[] banner = image(3000, 1000, "jpg");

        expect(hr.multipart(BASE + "/logo", Map.of("file", new TestApi.FilePart("logo.png", "image/png", logo))),
                200);
        expect(hr.multipart(BASE + "/banner",
                Map.of("file", new TestApi.FilePart("banner.jpg", "image/jpeg", banner))), 200);

        BufferedImage savedLogo = ImageIO.read(new ByteArrayInputStream(hr.getBytes(BASE + "/logo").body()));
        BufferedImage savedBanner = ImageIO.read(new ByteArrayInputStream(hr.getBytes(BASE + "/banner").body()));
        assertThat(savedLogo.getHeight()).isEqualTo(120);
        assertThat(savedLogo.getWidth()).isEqualTo(240);
        assertThat(savedBanner.getWidth()).isEqualTo(1200);
        assertThat(savedBanner.getHeight()).isEqualTo(400);

        byte[] fake = {(byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n', 1, 2, 3};
        expect(hr.multipart(BASE + "/logo", Map.of("file", new TestApi.FilePart("fake.png", "image/png", fake))),
                400);
    }

    /** 20px 칸마다 색이 다른 그림. */
    private static byte[] image(int width, int height, String format) {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Random random = new Random(7);
        int[] colors = random.ints(64, 0, 0xffffff).toArray();
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                image.setRGB(x, y, colors[(x / 20 + y / 20 * 7) % colors.length]);
            }
        }
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try {
            ImageIO.write(image, format, out);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
        return out.toByteArray();
    }

    @Test
    @DisplayName("메일 색은 기본 남색이고, 색 코드는 #를 빼거나 대문자로 넣어도 #rrggbb로 저장하며 6자리가 아니면 거절한다")
    void colorIsNormalizedAndValidated() throws Exception {
        TestApi hr = newHr();
        assertThat(json(expect(hr.get(BASE), 200)).path("color").asString()).isEqualTo("#1e3a5f");

        JsonNode saved = json(expect(hr.put(BASE, Map.of("color", "0055A4")), 200));
        assertThat(saved.path("color").asString()).isEqualTo("#0055a4");
        assertThat(saved.path("hasLogo").asBoolean()).isFalse();
        expect(hr.put(BASE, Map.of("color", "#12345")), 400);
        expect(hr.put(BASE, Map.of("color", "red")), 400);
        expect(hr.get(BASE + "/preview?color=blue"), 400);

        String preview = json(expect(hr.get(BASE + "/preview?color=%23ff0000"), 200)).path("html").asString();
        assertThat(preview).contains("background:#ff0000;", ">1차 면접 안내</td>", "홍길동님");
        assertThat(json(expect(hr.get(BASE + "/preview"), 200)).path("html").asString()).contains("#0055a4");
        assertThat(json(expect(newHr().get(BASE), 200)).path("color").asString()).isEqualTo("#1e3a5f");
    }

    @Test
    @DisplayName("보조 색과 머리 · 안내 상자 모양을 저장하고, 빼면 보조 색 없이 얇은 줄과 옅은 바탕으로 돌아간다")
    void lookIsSavedWithAccentAndParts() throws Exception {
        TestApi hr = newHr();
        JsonNode initial = json(expect(hr.get(BASE), 200));
        assertThat(initial.path("accent").isNull()).isTrue();
        assertThat(initial.path("header").asString()).isEqualTo("LINE");
        assertThat(initial.path("box").asString()).isEqualTo("FILL");

        JsonNode saved = json(expect(hr.put(BASE, Map.of("color", "#0055a4", "accent", "F97316", "header", "BAND",
                "box", "OUTLINE")), 200));
        assertThat(saved.path("accent").asString()).isEqualTo("#f97316");
        assertThat(saved.path("header").asString()).isEqualTo("BAND");
        assertThat(saved.path("box").asString()).isEqualTo("OUTLINE");
        assertThat(json(expect(hr.get(BASE + "/preview"), 200)).path("html").asString())
                .contains("padding:18px 32px;background:#0055a4;", "border:1px solid #f97316;");
        expect(hr.put(BASE, Map.of("color", "#0055a4", "accent", "orange")), 400);
        expect(hr.put(BASE, Map.of("color", "#0055a4", "header", "WAVE")), 400);

        JsonNode reset = json(expect(hr.put(BASE, Map.of("color", "#0055a4")), 200));
        assertThat(reset.path("accent").isNull()).isTrue();
        assertThat(reset.path("header").asString()).isEqualTo("LINE");
        assertThat(reset.path("box").asString()).isEqualTo("FILL");

        String draft = json(expect(hr.get(BASE + "/preview?color=%230055a4&accent=%23f97316&header=CENTER&box=ROWS"),
                200)).path("html").asString();
        assertThat(draft).contains("text-align:center;", "border-left:4px solid #f97316;");
    }

    @Test
    @DisplayName("배너는 PNG · JPEG만 5MB까지 받고, 배너 머리면 메일 맨 위에 넣어 보내며 지우면 색 띠로 돌아간다")
    void bannerIsShownAndSent() throws Exception {
        TestApi hr = newHr();
        byte[] large = Arrays.copyOf(PNG, 5 * 1024 * 1024 + 1);
        assertThat(json(expect(hr.multipart(BASE + "/banner",
                Map.of("file", new TestApi.FilePart("big.png", "image/png", large))), 400)).path("code").asString())
                .isEqualTo("BANNER_TOO_LARGE");
        JsonNode uploaded = json(expect(hr.multipart(BASE + "/banner",
                Map.of("file", new TestApi.FilePart("banner.png", "image/png", PNG))), 200));
        assertThat(uploaded.path("hasBanner").asBoolean()).isTrue();
        assertThat(hr.getBytes(BASE + "/banner").body()).isEqualTo(PNG);
        expect(hr.put(BASE, Map.of("color", "#0055a4", "header", "BANNER")), 200);
        assertThat(json(expect(hr.get(BASE + "/preview"), 200)).path("html").asString())
                .contains("<img src=\"data:image/png;base64,", "width=\"600\"");

        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String posting = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        expect(hr.put(posting, Map.of("title", "결제 백엔드 개발자", "jobCategory", "", "employmentType", "",
                "career", "", "location", "", "intro", "", "duties", List.of(), "qualifications", List.of(),
                "preferred", List.of(), "benefits", List.of())), 200);
        Instant now = Instant.now();
        expect(hr.post(posting + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);
        expect(anonymous().multipart("/api/public/postings/" + draft.path("postingId").asString() + "/applications",
                TestFixtures.form("banner@example.com", false)), 201);
        int index = awaitMail("banner@example.com");
        assertThat(mail.html.get(index)).contains("<img src=\"cid:company-banner\"");
        assertThat(mail.banners.get(index)).isEqualTo("image/png");

        assertThat(json(expect(hr.delete(BASE + "/banner"), 200)).path("hasBanner").asBoolean()).isFalse();
        expect(hr.get(BASE + "/banner"), 404);
        assertThat(json(expect(hr.get(BASE + "/preview"), 200)).path("html").asString())
                .contains("padding:18px 32px;background:#0055a4;").doesNotContain("<img");
    }

    @Test
    @DisplayName("로고는 PNG · JPEG만 5MB까지 받고, 올리면 미리보기에 보이며 지운 뒤에는 회사 이름 글자로 돌아간다")
    void logoIsCheckedShownAndRemoved() throws Exception {
        TestApi hr = newHr();
        expect(hr.multipart(BASE + "/logo", Map.of("file", new TestApi.FilePart("logo.png", "image/png",
                "%PDF-1.4".getBytes(StandardCharsets.US_ASCII)))), 400);
        byte[] large = Arrays.copyOf(PNG, 5 * 1024 * 1024 + 1);
        assertThat(json(expect(hr.multipart(BASE + "/logo",
                Map.of("file", new TestApi.FilePart("big.png", "image/png", large))), 400)).path("code").asString())
                .isEqualTo("LOGO_TOO_LARGE");

        JsonNode uploaded = json(expect(hr.multipart(BASE + "/logo",
                Map.of("file", new TestApi.FilePart("logo.png", "image/png", PNG))), 200));
        assertThat(uploaded.path("hasLogo").asBoolean()).isTrue();
        HttpResponse<byte[]> logo = hr.getBytes(BASE + "/logo");
        assertThat(logo.body()).isEqualTo(PNG);
        assertThat(logo.headers().firstValue("Content-Type")).hasValue("image/png");
        assertThat(json(expect(hr.get(BASE + "/preview"), 200)).path("html").asString())
                .contains("<img src=\"data:image/png;base64,");

        assertThat(json(expect(hr.delete(BASE + "/logo"), 200)).path("hasLogo").asBoolean()).isFalse();
        expect(hr.get(BASE + "/logo"), 404);
        assertThat(json(expect(hr.get(BASE + "/preview"), 200)).path("html").asString()).doesNotContain("<img");
    }

    @Test
    @DisplayName("접수 확인 메일은 기업이 고른 색으로 꾸미고 로고를 메일 안에 함께 넣어 보낸다")
    void receiptMailCarriesBrand() throws Exception {
        TestApi hr = newHr();
        expect(hr.put(BASE, Map.of("color", "#0055a4")), 200);
        expect(hr.multipart(BASE + "/logo", Map.of("file", new TestApi.FilePart("logo.png", "image/png", PNG))),
                200);
        JsonNode draft = json(expect(hr.post("/api/recruitments", null), 201));
        String posting = "/api/recruitments/" + draft.path("recruitmentId").asString() + "/posting";
        expect(hr.put(posting, Map.of("title", "결제 백엔드 개발자", "jobCategory", "", "employmentType", "",
                "career", "", "location", "", "intro", "", "duties", List.of(), "qualifications", List.of(),
                "preferred", List.of(), "benefits", List.of())), 200);
        assertThat(json(expect(hr.get(posting + "/receipt/preview"), 200)).path("html").asString())
                .contains("background:#0055a4;", "data:image/png;base64,");
        Instant now = Instant.now();
        expect(hr.post(posting + "/publish", Map.of("openAt", now.minus(1, ChronoUnit.HOURS).toString(),
                "closeAt", now.plus(3, ChronoUnit.DAYS).toString())), 200);

        Map<String, Object> form = TestFixtures.form("brand@example.com", false);
        expect(anonymous().multipart("/api/public/postings/" + draft.path("postingId").asString() + "/applications",
                form), 201);
        int index = awaitMail("brand@example.com");
        assertThat(mail.html.get(index)).contains("background:#0055a4;", "<img src=\"cid:company-logo\"");
        assertThat(mail.logos.get(index)).isEqualTo("image/png");
    }

    /** 접수 확인 메일은 접수가 끝난 뒤 따로 보내져 잠깐 기다린다. 보낸 순서를 돌려준다. */
    private int awaitMail(String to) throws InterruptedException {
        Instant deadline = Instant.now().plus(Duration.ofSeconds(10));
        while (Instant.now().isBefore(deadline)) {
            for (int index = 0; index < mail.logos.size(); index++) {
                if (mail.sent.get(index).startsWith(to + "|")) {
                    return index;
                }
            }
            Thread.sleep(100);
        }
        throw new AssertionError("Receipt mail was not sent.");
    }
}
