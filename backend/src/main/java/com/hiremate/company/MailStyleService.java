package com.hiremate.company;

import com.hiremate.company.domain.CompanyMailStyle;
import com.hiremate.company.domain.CompanyMailStyleRepository;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.file.StoredFileInfo;
import com.hiremate.global.ApiException;
import com.hiremate.mail.MailBrand;
import com.hiremate.mail.MailBrand.GuideBox;
import com.hiremate.mail.MailBrand.Header;
import com.hiremate.mail.MailContent;
import com.hiremate.mail.MailPreview;
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.imageio.IIOImage;
import javax.imageio.ImageIO;
import javax.imageio.ImageWriteParam;
import javax.imageio.ImageWriter;
import javax.imageio.stream.ImageOutputStream;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 메일 꾸밈(대표 색, 머리와 안내 상자 모양, 로고, 배너). 기업 설정에서 고르고,
 * 모든 안내 메일과 접수 확인 메일이 같이 쓴다.
 * 로고와 배너는 5MB까지 PNG, JPEG만 받는다. 파일 내용으로 형식을 확인한다.
 * 그림은 메일마다 함께 넣어 보내서, 메일에 보이는 크기에 맞춰 줄여 저장한다.
 * 로고는 높이 120px(메일에서 40px로 보이는 크기의 3배), 배너는 너비 1200px(메일 폭의 2배)까지다.
 */
@Service
public class MailStyleService {

    static final int UPLOAD_MAX_BYTES = 5 * 1024 * 1024;
    static final Fit LOGO = new Fit(660, 120, 500 * 1024);
    static final Fit BANNER = new Fit(1200, 600, 1024 * 1024);
    private static final Pattern COLOR = Pattern.compile("^#?([0-9a-fA-F]{6})$");
    private static final byte[] PNG = {(byte) 0x89, 'P', 'N', 'G', '\r', '\n', 0x1a, '\n'};
    private static final byte[] JPEG = {(byte) 0xff, (byte) 0xd8, (byte) 0xff};

    private final CompanyMailStyleRepository styles;
    private final CompanyService companies;
    private final FileService files;

    public MailStyleService(CompanyMailStyleRepository styles, CompanyService companies, FileService files) {
        this.styles = styles;
        this.companies = companies;
        this.files = files;
    }

    @Transactional(readOnly = true)
    public MailStyle mailStyle(UUID companyId) {
        return styles.findById(companyId).map(MailStyleService::toView)
                .orElseGet(() -> new MailStyle(MailBrand.DEFAULT_COLOR, Header.LINE, GuideBox.FILL, false, false));
    }

    /** 색과 부품을 저장한다. 색 코드는 앞의 #를 빼거나 대문자로 넣어도 받는다. 저장은 #rrggbb다. */
    @Transactional
    public MailStyle changeLook(UUID companyId, MailLook look) {
        CompanyMailStyle style = style(companyId);
        style.changeLook(normalize(look.color()), look.header(), look.box());
        return toView(style);
    }

    @Transactional
    public MailStyle changeLogo(UUID companyId, String name, byte[] content) {
        UUID fileId = store(companyId, name, "logo", content, LOGO, "LOGO_TOO_LARGE");
        CompanyMailStyle style = style(companyId);
        style.changeLogo(fileId);
        return toView(style);
    }

    @Transactional
    public MailStyle deleteLogo(UUID companyId) {
        CompanyMailStyle style = style(companyId);
        style.changeLogo(null);
        return toView(style);
    }

    /** 설정 화면에 보여 줄 로고 그림. */
    @Transactional(readOnly = true)
    public FileContent logo(UUID companyId) {
        UUID fileId = styles.findById(companyId).map(CompanyMailStyle::getLogoFileId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "LOGO_NOT_FOUND", "No logo has been uploaded."));
        return files.read(companyId, fileId);
    }

    /** 배너 머리에 쓰는 그림. 메일 폭(600px)에 맞춰 줄여 보인다. */
    @Transactional
    public MailStyle changeBanner(UUID companyId, String name, byte[] content) {
        UUID fileId = store(companyId, name, "banner", content, BANNER, "BANNER_TOO_LARGE");
        CompanyMailStyle style = style(companyId);
        style.changeBanner(fileId);
        return toView(style);
    }

    @Transactional
    public MailStyle deleteBanner(UUID companyId) {
        CompanyMailStyle style = style(companyId);
        style.changeBanner(null);
        return toView(style);
    }

    /**
     * 참고 그림(로고, 배너, 예전 메일)에서 대표 색과 보조 색을 고른다. 저장하지 않는다.
     * 모델을 부르지 않고 코드 규칙으로만 고른다 ({@link MailColorPicker}).
     */
    public MailColorSuggestion suggestColors(byte[] content) {
        if (content.length > UPLOAD_MAX_BYTES) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "IMAGE_TOO_LARGE", "The image must be 5MB or smaller.");
        }
        imageType(content);
        return MailColorPicker.pick(read(content));
    }

    /** 설정 화면에 보여 줄 배너 그림. */
    @Transactional(readOnly = true)
    public FileContent banner(UUID companyId) {
        UUID fileId = styles.findById(companyId).map(CompanyMailStyle::getBannerFileId).orElseThrow(
                () -> new ApiException(HttpStatus.NOT_FOUND, "BANNER_NOT_FOUND", "No banner has been uploaded."));
        return files.read(companyId, fileId);
    }

    /**
     * 메일을 보낼 때 쓰는 꾸밈. 로고나 배너 파일을 읽지 못하면 그 그림 없이 보낸다 (메일은 막지 않는다).
     * 부르는 쪽의 트랜잭션 밖에서 읽는다. 그림 읽기가 실패해도 안내 발송 기록이 함께 롤백되지 않는다.
     */
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public MailBrand brand(UUID companyId) {
        return styles.findById(companyId).map(style -> new MailBrand(
                style.getColor() == null ? MailBrand.DEFAULT_COLOR : style.getColor(), style.getHeader(),
                style.getGuideBox(), image(companyId, style.getLogoFileId()),
                image(companyId, style.getBannerFileId()))).orElse(MailBrand.BASIC);
    }

    /**
     * 저장 전 색과 부품에 저장한 로고와 배너를 더한 꾸밈. 설정 화면의 미리보기가 쓴다.
     *
     * @param draft 저장 전 색과 부품. null이면 저장한 꾸밈이다
     */
    public MailBrand brand(UUID companyId, MailLook draft) {
        MailBrand saved = brand(companyId);
        return draft == null ? saved
                : new MailBrand(normalize(draft.color()), draft.header(), draft.box(), saved.logo(), saved.banner());
    }

    /**
     * 설정 화면의 미리보기. 고르는 중인 색과 부품, 올린 로고와 배너로 다음 전형 안내 양식의 예시 메일을 만든다.
     *
     * 트랜잭션 없이 brand와 조회 메서드를 부른다. 그림을 못 읽어도 그 그림 없이 보여 준다.
     *
     * @param draft 저장 전 색과 부품. null이면 저장한 꾸밈이다
     */
    public MailPreview preview(UUID companyId, MailLook draft) {
        MailBrand brand = brand(companyId, draft);
        String companyName = companies.profile(companyId).name();
        NoticeTemplateInfo template = companies.noticeTemplate(companyId, NoticeTemplateType.NEXT_STAGE);
        Map<String, String> values = Map.of("{지원자명}", "홍길동", "{회사명}", companyName, "{공고명}", "예시 공고",
                "{전형명}", "서류 전형");
        MailContent sample = new MailContent(companyName, "예시 공고", List.of(
                new MailContent.Text(template.greeting()),
                new MailContent.Text("서류 전형에 합격하셨음을 알려드리며, 진심으로 축하드립니다.\n\n다음 전형은 1차 면접입니다."),
                new MailContent.Guide("일정과 준비 사항은 아래 안내를 확인해 주시기 바랍니다.", "1차 면접 안내",
                        List.of(new MailContent.Item("일정", "11월 12일(목) 오후 2시"),
                                new MailContent.Item("장소·접속 링크", "본사 5층 회의실")),
                        List.of("참석 여부를 미리 알려 주세요"))),
                template.closing(), template.requiredText()).fill(values);
        String subject = template.subject();
        for (Map.Entry<String, String> value : values.entrySet()) {
            subject = subject.replace(value.getKey(), value.getValue());
        }
        return MailPreview.of(subject, sample, brand);
    }

    static String normalize(String color) {
        Matcher matcher = COLOR.matcher(color == null ? "" : color.strip());
        if (!matcher.matches()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_COLOR", "Use a 6-digit color code like #0055A4.");
        }
        return "#" + matcher.group(1).toLowerCase(Locale.ROOT);
    }

    private UUID store(UUID companyId, String name, String fallback, byte[] content, Fit fit, String tooLarge) {
        if (content.length > UPLOAD_MAX_BYTES) {
            throw new ApiException(HttpStatus.BAD_REQUEST, tooLarge, "The image must be 5MB or smaller.");
        }
        String type = imageType(content);
        byte[] fitted = shrink(content, type, fit);
        if (fitted.length > fit.maxBytes()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, tooLarge, "The image could not be made small enough.");
        }
        String fileName = name == null || name.isBlank() ? fallback : name;
        StoredFileInfo stored = files.store(companyId, fileName, type, fitted);
        return stored.fileId();
    }

    /**
     * 그림을 fit 안으로 비율대로 줄인다. 이미 크기와 용량이 맞으면 화질을 지키려고 그대로 둔다.
     * PNG는 투명한 곳을 지키고, JPEG은 품질 0.9로 다시 저장한다.
     */
    static byte[] shrink(byte[] content, String type, Fit fit) {
        BufferedImage image = read(content);
        double scale = Math.min(1.0, Math.min((double) fit.maxWidth() / image.getWidth(),
                (double) fit.maxHeight() / image.getHeight()));
        if (scale == 1.0 && content.length <= fit.maxBytes()) {
            return content;
        }
        boolean png = type.equals("image/png");
        int width = Math.max(1, (int) Math.round(image.getWidth() * scale));
        int height = Math.max(1, (int) Math.round(image.getHeight() * scale));
        BufferedImage resized = new BufferedImage(width, height,
                png ? BufferedImage.TYPE_INT_ARGB : BufferedImage.TYPE_INT_RGB);
        Graphics2D graphics = resized.createGraphics();
        graphics.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BICUBIC);
        graphics.setRenderingHint(RenderingHints.KEY_RENDERING, RenderingHints.VALUE_RENDER_QUALITY);
        if (!png) {
            graphics.setColor(Color.WHITE);
            graphics.fillRect(0, 0, width, height);
        }
        graphics.drawImage(image, 0, 0, width, height, null);
        graphics.dispose();
        return encode(resized, png);
    }

    /** 형식만 맞고 읽을 수 없는 그림은 거절한다. */
    private static BufferedImage read(byte[] content) {
        BufferedImage image;
        try {
            image = ImageIO.read(new ByteArrayInputStream(content));
        } catch (IOException unreadable) {
            image = null;
        }
        if (image == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_LOGO", "The image could not be read.");
        }
        return image;
    }

    private static byte[] encode(BufferedImage image, boolean png) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try {
            if (png) {
                ImageIO.write(image, "png", out);
                return out.toByteArray();
            }
            ImageWriter writer = ImageIO.getImageWritersByFormatName("jpg").next();
            ImageWriteParam param = writer.getDefaultWriteParam();
            param.setCompressionMode(ImageWriteParam.MODE_EXPLICIT);
            param.setCompressionQuality(0.9f);
            try (ImageOutputStream stream = ImageIO.createImageOutputStream(out)) {
                writer.setOutput(stream);
                writer.write(null, new IIOImage(image, null, null), param);
            } finally {
                writer.dispose();
            }
            return out.toByteArray();
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    /** 그림을 줄여 넣을 최대 너비와 높이(px), 줄인 뒤 받을 수 있는 최대 용량. */
    record Fit(int maxWidth, int maxHeight, int maxBytes) {
    }

    private MailBrand.Logo image(UUID companyId, UUID fileId) {
        if (fileId == null) {
            return null;
        }
        try {
            FileContent image = files.read(companyId, fileId);
            return new MailBrand.Logo(image.bytes(), image.info().contentType());
        } catch (RuntimeException unreadable) {
            return null;
        }
    }

    static String imageType(byte[] content) {
        if (startsWith(content, PNG)) {
            return "image/png";
        }
        if (startsWith(content, JPEG)) {
            return "image/jpeg";
        }
        throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_LOGO", "Only PNG or JPEG images are allowed.");
    }

    private static boolean startsWith(byte[] content, byte[] prefix) {
        if (content.length < prefix.length) {
            return false;
        }
        for (int index = 0; index < prefix.length; index++) {
            if (content[index] != prefix[index]) {
                return false;
            }
        }
        return true;
    }

    private CompanyMailStyle style(UUID companyId) {
        return styles.findById(companyId).orElseGet(() -> styles.save(new CompanyMailStyle(companyId)));
    }

    private static MailStyle toView(CompanyMailStyle style) {
        return new MailStyle(style.getColor() == null ? MailBrand.DEFAULT_COLOR : style.getColor(),
                style.getHeader(), style.getGuideBox(), style.getLogoFileId() != null, style.getBannerFileId() != null);
    }
}
