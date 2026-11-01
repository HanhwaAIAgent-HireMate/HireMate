package com.hiremate.company;

import static com.hiremate.TestApi.expect;
import static com.hiremate.TestApi.json;
import static org.assertj.core.api.Assertions.assertThat;

import com.hiremate.IntegrationTest;
import com.hiremate.TestApi;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.Map;
import java.util.Random;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;

class CompanyLogoTests extends IntegrationTest {

    private static final String BASE = "/api/companies/me/logo";
    private static final String MAIL = "/api/companies/me/mail-style";
    private static final String POSTER = "/api/companies/me/poster-brand";

    @Test
    @DisplayName("회사 로고를 한 번 올리면 메일용은 메일 머리 크기로, 포스터용은 포스터 한도 안으로 줄여 저장하고 "
            + "메일과 포스터 색을 로고에 맞춘다")
    void oneLogoServesMailAndPoster() throws Exception {
        TestApi hr = newHr();
        String posterColor = json(expect(hr.get(POSTER), 200)).path("color").asString();

        expect(hr.multipart(BASE, Map.of("file", new TestApi.FilePart("logo.png", "image/png", blocks(2400, 1200)))),
                204);

        BufferedImage shown = ImageIO.read(new ByteArrayInputStream(hr.getBytes(BASE).body()));
        assertThat(shown.getHeight()).isEqualTo(120);
        JsonNode mail = json(expect(hr.get(MAIL), 200));
        assertThat(mail.path("hasLogo").asBoolean()).isTrue();
        assertThat(mail.path("color").asString()).isNotEqualTo("#1e3a5f");
        JsonNode poster = json(expect(hr.get(POSTER), 200));
        assertThat(poster.path("logoFileId").isNull()).isFalse();
        assertThat(poster.path("color").asString()).isNotEqualTo(posterColor);
        byte[] posterLogo = hr.getBytes(POSTER + "/logo").body();
        BufferedImage posterImage = ImageIO.read(new ByteArrayInputStream(posterLogo));
        assertThat(posterLogo.length).isLessThanOrEqualTo(500 * 1024);
        assertThat(posterImage.getWidth()).isEqualTo(1600);
    }

    @Test
    @DisplayName("메일 대표 색은 로고에서 가장 넓은 브랜드 색이 되고, 흑백 로고면 그대로 둔다")
    void mailColorFollowsLogo() throws Exception {
        TestApi hr = newHr();
        BufferedImage navy = new BufferedImage(300, 100, BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = navy.createGraphics();
        graphics.setColor(new Color(0x1b2a4a));
        graphics.fillRect(0, 0, 300, 100);
        graphics.setColor(new Color(0xc2410c));
        graphics.fillRect(200, 20, 80, 60);
        graphics.dispose();

        expect(hr.multipart(BASE, Map.of("file", new TestApi.FilePart("navy.png", "image/png", png(navy)))), 204);
        assertThat(json(expect(hr.get(MAIL), 200)).path("color").asString()).isEqualTo("#1b2a4a");

        BufferedImage gray = new BufferedImage(300, 100, BufferedImage.TYPE_INT_RGB);
        graphics = gray.createGraphics();
        graphics.setColor(Color.WHITE);
        graphics.fillRect(0, 0, 300, 100);
        graphics.setColor(Color.BLACK);
        graphics.fillRect(50, 30, 200, 40);
        graphics.dispose();

        expect(hr.multipart(BASE, Map.of("file", new TestApi.FilePart("gray.png", "image/png", png(gray)))), 204);
        assertThat(json(expect(hr.get(MAIL), 200)).path("color").asString()).isEqualTo("#1b2a4a");
    }

    @Test
    @DisplayName("사진처럼 잘 안 줄어드는 그림도 포스터용은 500KB 안으로 줄여 받는다")
    void photoLikeLogoFitsPosterLimit() throws Exception {
        TestApi hr = newHr();
        byte[] noise = noise(1000, 800);
        assertThat(noise.length).isGreaterThan(500 * 1024);

        expect(hr.multipart(BASE, Map.of("file", new TestApi.FilePart("photo.png", "image/png", noise))), 204);

        assertThat(hr.getBytes(POSTER + "/logo").body().length).isLessThanOrEqualTo(500 * 1024);
    }

    @Test
    @DisplayName("로고를 지우면 메일과 포스터 모두에서 빠지고, 5MB를 넘거나 그림이 아니면 아무것도 저장하지 않는다")
    void deleteAndRejectTouchBoth() throws Exception {
        TestApi hr = newHr();
        expect(hr.multipart(BASE, Map.of("file", new TestApi.FilePart("logo.png", "image/png", blocks(400, 200)))),
                204);

        expect(hr.delete(BASE), 204);
        assertThat(json(expect(hr.get(MAIL), 200)).path("hasLogo").asBoolean()).isFalse();
        assertThat(json(expect(hr.get(POSTER), 200)).path("logoFileId").isNull()).isTrue();

        byte[] fake = {(byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n', 1, 2, 3};
        expect(hr.multipart(BASE, Map.of("file", new TestApi.FilePart("fake.png", "image/png", fake))), 400);
        expect(hr.multipart(BASE, Map.of("file", new TestApi.FilePart("big.png", "image/png",
                new byte[5 * 1024 * 1024 + 1]))), 400);
        assertThat(json(expect(hr.get(MAIL), 200)).path("hasLogo").asBoolean()).isFalse();
        assertThat(json(expect(hr.get(POSTER), 200)).path("logoFileId").isNull()).isTrue();
    }

    /** 20px 칸마다 색이 다른 그림. 칸이 커서 PNG로 잘 줄어든다. */
    private static byte[] blocks(int width, int height) {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        int[] colors = new Random(7).ints(64, 0, 0xffffff).toArray();
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                image.setRGB(x, y, colors[(x / 20 + y / 20 * 7) % colors.length]);
            }
        }
        return png(image);
    }

    /** 점마다 색이 다른 그림. 사진처럼 PNG로 잘 안 줄어든다. */
    private static byte[] noise(int width, int height) {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        Random random = new Random(11);
        for (int y = 0; y < height; y++) {
            for (int x = 0; x < width; x++) {
                image.setRGB(x, y, random.nextInt(0xffffff));
            }
        }
        return png(image);
    }

    private static byte[] png(BufferedImage image) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try {
            ImageIO.write(image, "png", out);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
        return out.toByteArray();
    }
}
