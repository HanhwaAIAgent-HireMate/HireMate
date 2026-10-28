package com.hiremate.company;

import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.file.StoredFileInfo;
import com.hiremate.global.ApiException;
import java.awt.Color;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.HashMap;
import java.util.Iterator;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 포스터 전용 로고. 검증한 작은 이미지만 저장하고, 유채색 대표 색상을 추출한다. */
@Service
public class PosterBrandService {

    private final CompanyService companies;
    private final FileService files;

    public PosterBrandService(CompanyService companies, FileService files) {
        this.companies = companies;
        this.files = files;
    }

    @Transactional
    public PosterBrand upload(UUID companyId, String name, byte[] bytes) {
        if (bytes.length == 0 || bytes.length > 500 * 1024) {
            throw invalid("로고는 500KB 이하의 PNG 또는 JPEG 이미지여야 해요.");
        }
        try (ImageInputStream input = ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))) {
            Iterator<ImageReader> readers = ImageIO.getImageReaders(input);
            if (!readers.hasNext()) {
                throw invalid("PNG 또는 JPEG 이미지를 선택해 주세요.");
            }
            ImageReader reader = readers.next();
            try {
                reader.setInput(input);
                String format = reader.getFormatName().toLowerCase(Locale.ROOT);
                if (!(format.equals("png") || format.equals("jpeg"))
                        || (long) reader.getWidth(0) * reader.getHeight(0) > 4_000_000) {
                    throw invalid("PNG 또는 JPEG, 400만 화소 이하 이미지를 선택해 주세요.");
                }
                BufferedImage image = reader.read(0);
                PosterBrand previous = companies.posterBrand(companyId);
                String color = dominantColor(image, previous.color());
                StoredFileInfo file = files.store(companyId, name == null ? "logo" : name,
                        "image/" + format, bytes);
                return companies.updatePosterBrand(companyId, new PosterBrand(previous.template(), previous.mood(),
                        color, previous.decoration(), file.fileId(), previous.templates()));
            } finally {
                reader.dispose();
            }
        } catch (IOException exception) {
            throw invalid("로고 이미지를 읽지 못했어요.");
        }
    }

    @Transactional
    public PosterBrand delete(UUID companyId) {
        PosterBrand previous = companies.posterBrand(companyId);
        return companies.updatePosterBrand(companyId, new PosterBrand(previous.template(), previous.mood(),
                previous.color(), previous.decoration(), null, previous.templates()));
    }

    @Transactional(readOnly = true)
    public FileContent logo(UUID companyId) {
        UUID id = companies.posterBrand(companyId).logoFileId();
        if (id == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "LOGO_NOT_FOUND", "등록된 포스터 로고가 없어요.");
        }
        return files.read(companyId, id);
    }

    static String dominantColor(BufferedImage image, String fallback) {
        Map<Integer, Integer> counts = new HashMap<>();
        int step = Math.max(1, Math.max(image.getWidth(), image.getHeight()) / 100);
        for (int y = 0; y < image.getHeight(); y += step) {
            for (int x = 0; x < image.getWidth(); x += step) {
                int pixel = image.getRGB(x, y);
                Color color = new Color(pixel, true);
                float[] hsb = Color.RGBtoHSB(color.getRed(), color.getGreen(), color.getBlue(), null);
                if (color.getAlpha() >= 128 && hsb[1] >= 0.15 && hsb[2] >= 0.15) {
                    int bucket = ((color.getRed() >> 4) << 8) | ((color.getGreen() >> 4) << 4)
                            | (color.getBlue() >> 4);
                    counts.merge(bucket, 1, Integer::sum);
                }
            }
        }
        return counts.entrySet().stream().sorted(Map.Entry.<Integer, Integer>comparingByValue().reversed()
                .thenComparing(Map.Entry.comparingByKey())).findFirst().map(entry -> {
                    int value = entry.getKey();
                    return String.format(Locale.ROOT, "#%02x%02x%02x", ((value >> 8) & 15) * 16 + 8,
                            ((value >> 4) & 15) * 16 + 8, (value & 15) * 16 + 8);
                }).orElse(fallback);
    }

    private static ApiException invalid(String message) {
        return new ApiException(HttpStatus.BAD_REQUEST, "INVALID_POSTER_LOGO", message);
    }
}
