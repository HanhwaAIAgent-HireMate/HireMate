package com.hiremate.company;

import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

/**
 * 참고 그림(로고, 배너, 예전 메일)에서 메일 색을 고른다. 모델 없이 코드 규칙으로만 고르며 같은 그림에는 늘 같은 답이다.
 *
 * 1. 불투명한 점의 색을 채널마다 16단계로 묶어 많이 쓰인 순서로 센다.
 * 2. 회색 · 흰색 · 검은색처럼 회사 색이 아닌 색(채도 0.25 미만, 밝기 0.93 초과나 0.15 미만)은 뺀다.
 * 3. 서로 비슷한 색(채널 차이 합 40 이하)은 많이 쓰인 쪽으로 합친다.
 * 4. 대표 색은 가장 많이 쓰인 색, 보조 색은 대표 색과 색상이 40도 이상 다른 색 가운데 가장 많이 쓰인 색이다.
 *    둘 다 흰 바탕 글자로 쓰여서 흰색과의 명암비가 3:1에 못 미치면 같은 색상으로 어둡게 맞춘다.
 */
final class MailColorPicker {

    static final int MAX_CANDIDATES = 5;
    private static final int SAMPLE_SIZE = 200;
    private static final double MIN_SHARE = 0.01;
    private static final double MIN_SATURATION = 0.25;
    private static final double MAX_LIGHTNESS = 0.93;
    private static final double MIN_LIGHTNESS = 0.15;
    private static final int NEAR = 40;
    private static final double MIN_HUE_GAP = 40;
    private static final double MIN_CONTRAST = 3.0;

    private MailColorPicker() {
    }

    static MailColorSuggestion pick(BufferedImage image) {
        List<Swatch> swatches = merge(count(sample(image)));
        int total = swatches.isEmpty() ? 0 : swatches.getFirst().total;
        List<Swatch> brandLike = swatches.stream()
                .filter(swatch -> (double) swatch.count / total >= MIN_SHARE && brandLike(swatch.rgb()))
                .limit(MAX_CANDIDATES)
                .toList();
        List<MailColorSuggestion.ColorCandidate> candidates = brandLike.stream()
                .map(swatch -> new MailColorSuggestion.ColorCandidate(hex(swatch.rgb()),
                        (double) swatch.count / total))
                .toList();
        if (brandLike.isEmpty()) {
            return new MailColorSuggestion(null, null, candidates);
        }
        int[] main = brandLike.getFirst().rgb();
        String accent = brandLike.stream().skip(1)
                .filter(swatch -> hueGap(hue(swatch.rgb()), hue(main)) >= MIN_HUE_GAP)
                .findFirst()
                .map(swatch -> hex(readable(swatch.rgb())))
                .orElse(null);
        return new MailColorSuggestion(hex(readable(main)), accent, candidates);
    }

    /** 긴 쪽을 200px로 줄여 센다. 색의 비율은 거의 같고 큰 그림도 빨리 끝난다. */
    private static BufferedImage sample(BufferedImage image) {
        double scale = Math.min(1.0, (double) SAMPLE_SIZE / Math.max(image.getWidth(), image.getHeight()));
        if (scale == 1.0) {
            return image;
        }
        int width = Math.max(1, (int) Math.round(image.getWidth() * scale));
        int height = Math.max(1, (int) Math.round(image.getHeight() * scale));
        BufferedImage small = new BufferedImage(width, height, BufferedImage.TYPE_INT_ARGB);
        Graphics2D graphics = small.createGraphics();
        graphics.drawImage(image, 0, 0, width, height, null);
        graphics.dispose();
        return small;
    }

    /** 채널마다 16단계 칸에 넣어 세고, 칸마다 실제 색의 평균을 낸다. 반투명보다 더 투명한 점은 뺀다. */
    private static List<Swatch> count(BufferedImage image) {
        long[][] bins = new long[4096][4];
        int total = 0;
        for (int y = 0; y < image.getHeight(); y++) {
            for (int x = 0; x < image.getWidth(); x++) {
                int argb = image.getRGB(x, y);
                if ((argb >>> 24) < 128) {
                    continue;
                }
                int r = argb >> 16 & 0xff;
                int g = argb >> 8 & 0xff;
                int b = argb & 0xff;
                long[] bin = bins[(r >> 4) << 8 | (g >> 4) << 4 | b >> 4];
                bin[0]++;
                bin[1] += r;
                bin[2] += g;
                bin[3] += b;
                total++;
            }
        }
        List<Swatch> swatches = new ArrayList<>();
        for (long[] bin : bins) {
            if (bin[0] > 0) {
                swatches.add(new Swatch((int) bin[0], (int) (bin[1] / bin[0]), (int) (bin[2] / bin[0]),
                        (int) (bin[3] / bin[0]), total));
            }
        }
        swatches.sort(Comparator.comparingInt((Swatch swatch) -> swatch.count).reversed());
        return swatches;
    }

    /** 많이 쓰인 색부터, 비슷한 색을 앞의 색에 합친다. 합친 색은 앞의 색 그대로 두고 수만 더한다. */
    private static List<Swatch> merge(List<Swatch> swatches) {
        List<Swatch> merged = new ArrayList<>();
        for (Swatch swatch : swatches) {
            merged.stream().filter(kept -> distance(kept.rgb(), swatch.rgb()) <= NEAR).findFirst().ifPresentOrElse(
                    kept -> kept.count += swatch.count, () -> merged.add(swatch));
        }
        merged.sort(Comparator.comparingInt((Swatch swatch) -> swatch.count).reversed());
        return merged;
    }

    private static boolean brandLike(int[] rgb) {
        double[] hsl = hsl(rgb);
        return hsl[1] >= MIN_SATURATION && hsl[2] <= MAX_LIGHTNESS && hsl[2] >= MIN_LIGHTNESS;
    }

    /** 흰 바탕에서 글자로 읽히게 같은 색상을 조금씩 어둡게 한다. */
    private static int[] readable(int[] rgb) {
        int[] color = rgb.clone();
        while (contrastWithWhite(color) < MIN_CONTRAST) {
            for (int index = 0; index < 3; index++) {
                color[index] = (int) Math.floor(color[index] * 0.92);
            }
        }
        return color;
    }

    private static double contrastWithWhite(int[] rgb) {
        double[] channels = new double[3];
        for (int index = 0; index < 3; index++) {
            double value = rgb[index] / 255.0;
            channels[index] = value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
        }
        double luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
        return 1.05 / (luminance + 0.05);
    }

    private static int distance(int[] a, int[] b) {
        return Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) + Math.abs(a[2] - b[2]);
    }

    private static double hueGap(double a, double b) {
        double gap = Math.abs(a - b) % 360;
        return gap > 180 ? 360 - gap : gap;
    }

    private static double hue(int[] rgb) {
        return hsl(rgb)[0];
    }

    /** 색상(0~360), 채도(0~1), 밝기(0~1). */
    private static double[] hsl(int[] rgb) {
        double r = rgb[0] / 255.0;
        double g = rgb[1] / 255.0;
        double b = rgb[2] / 255.0;
        double max = Math.max(r, Math.max(g, b));
        double min = Math.min(r, Math.min(g, b));
        double lightness = (max + min) / 2;
        double delta = max - min;
        if (delta == 0) {
            return new double[] {0, 0, lightness};
        }
        double saturation = delta / (1 - Math.abs(2 * lightness - 1));
        double hue;
        if (max == r) {
            hue = 60 * (((g - b) / delta) % 6);
        } else if (max == g) {
            hue = 60 * ((b - r) / delta + 2);
        } else {
            hue = 60 * ((r - g) / delta + 4);
        }
        return new double[] {hue < 0 ? hue + 360 : hue, saturation, lightness};
    }

    private static String hex(int[] rgb) {
        return String.format(Locale.ROOT, "#%02x%02x%02x", rgb[0], rgb[1], rgb[2]);
    }

    /** 센 색 하나. count는 합칠 때 늘어난다. total은 불투명한 점 전체 수다. */
    private static final class Swatch {

        private int count;
        private final int red;
        private final int green;
        private final int blue;
        private final int total;

        Swatch(int count, int red, int green, int blue, int total) {
            this.count = count;
            this.red = red;
            this.green = green;
            this.blue = blue;
            this.total = total;
        }

        int[] rgb() {
            return new int[] {red, green, blue};
        }
    }
}
