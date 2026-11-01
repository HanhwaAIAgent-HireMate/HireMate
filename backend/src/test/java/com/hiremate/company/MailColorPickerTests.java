package com.hiremate.company;

import static org.assertj.core.api.Assertions.assertThat;

import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class MailColorPickerTests {

    @Test
    @DisplayName("흰 바탕 · 회색 글자는 빼고 가장 많이 쓰인 회사 색을 대표 색으로 고른다")
    void picksBrandColorOverWhiteAndGray() {
        BufferedImage logo = image(400, 200, Color.WHITE);
        fill(logo, new Color(0x0f8a5f), 0, 0, 200, 200);
        fill(logo, new Color(0x6b7280), 220, 80, 160, 40);

        MailColorSuggestion picked = MailColorPicker.pick(logo);

        assertThat(picked.color()).isEqualTo("#0f8a5f");
        assertThat(picked.candidates()).extracting(MailColorSuggestion.ColorCandidate::color)
                .containsExactly("#0f8a5f");
        assertThat(picked.candidates().getFirst().share()).isBetween(0.49, 0.51);
    }

    @Test
    @DisplayName("밝은 회사 색은 같은 색상으로 어둡게 맞춰 흰 바탕에서 읽히게 한다")
    void darkensLightColor() {
        BufferedImage logo = image(200, 200, new Color(0xffd23f));

        MailColorSuggestion picked = MailColorPicker.pick(logo);

        assertThat(picked.candidates().getFirst().color()).isEqualTo("#ffd23f");
        assertThat(picked.color()).isNotEqualTo("#ffd23f");
        assertThat(hue(picked.color())).isBetween(40f, 52f);
        assertThat(Color.decode(picked.color()).getRed()).isLessThan(0xd0);
    }

    @Test
    @DisplayName("회색 · 흰색 · 검은색만 있거나 투명한 그림이면 대표 색이 없다")
    void noBrandColor() {
        BufferedImage gray = image(200, 100, Color.WHITE);
        fill(gray, Color.BLACK, 0, 0, 100, 100);
        fill(gray, new Color(0x9ca3af), 100, 0, 100, 100);
        BufferedImage clear = new BufferedImage(100, 100, BufferedImage.TYPE_INT_ARGB);

        assertThat(MailColorPicker.pick(gray).color()).isNull();
        assertThat(MailColorPicker.pick(gray).candidates()).isEmpty();
        assertThat(MailColorPicker.pick(clear).color()).isNull();
    }

    @Test
    @DisplayName("투명한 바탕은 세지 않는다")
    void ignoresTransparentBackground() {
        BufferedImage logo = new BufferedImage(200, 200, BufferedImage.TYPE_INT_ARGB);
        fill(logo, new Color(0x6d28d9), 50, 50, 50, 50);

        MailColorSuggestion picked = MailColorPicker.pick(logo);

        assertThat(picked.color()).isEqualTo("#6d28d9");
        assertThat(picked.candidates().getFirst().share()).isEqualTo(1.0);
    }

    private static BufferedImage image(int width, int height, Color background) {
        BufferedImage image = new BufferedImage(width, height, BufferedImage.TYPE_INT_RGB);
        fill(image, background, 0, 0, width, height);
        return image;
    }

    private static void fill(BufferedImage image, Color color, int x, int y, int width, int height) {
        Graphics2D graphics = image.createGraphics();
        graphics.setColor(color);
        graphics.fillRect(x, y, width, height);
        graphics.dispose();
    }

    private static float hue(String hex) {
        Color color = Color.decode(hex);
        return Color.RGBtoHSB(color.getRed(), color.getGreen(), color.getBlue(), null)[0] * 360;
    }
}
