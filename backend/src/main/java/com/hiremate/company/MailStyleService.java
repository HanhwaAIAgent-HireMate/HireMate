package com.hiremate.company;

import com.hiremate.company.domain.CompanyMailStyle;
import com.hiremate.company.domain.CompanyMailStyleRepository;
import com.hiremate.file.FileContent;
import com.hiremate.file.FileService;
import com.hiremate.file.StoredFileInfo;
import com.hiremate.global.ApiException;
import com.hiremate.mail.MailBrand;
import com.hiremate.mail.MailContent;
import com.hiremate.mail.MailPreview;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 메일 꾸밈(색, 로고). 기업 설정에서 고르고, 모든 안내 메일과 접수 확인 메일이 같이 쓴다.
 * 로고는 PNG, JPEG만 500KB까지 받는다. 파일 내용으로 형식을 확인한다.
 */
@Service
public class MailStyleService {

    static final int LOGO_MAX_BYTES = 500 * 1024;
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
                .orElseGet(() -> new MailStyle(MailBrand.DEFAULT_COLOR, false));
    }

    /** 색 코드는 앞의 #를 빼거나 대문자로 넣어도 받는다. 저장은 #rrggbb다. */
    @Transactional
    public MailStyle changeColor(UUID companyId, String color) {
        CompanyMailStyle style = style(companyId);
        style.changeColor(normalize(color));
        return toView(style);
    }

    @Transactional
    public MailStyle changeLogo(UUID companyId, String name, byte[] content) {
        if (content.length > LOGO_MAX_BYTES) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "LOGO_TOO_LARGE", "The logo must be 500KB or smaller.");
        }
        String type = imageType(content);
        String fileName = name == null || name.isBlank() ? "logo" : name;
        StoredFileInfo stored = files.store(companyId, fileName, type, content);
        CompanyMailStyle style = style(companyId);
        style.changeLogo(stored.fileId());
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

    /**
     * 메일을 보낼 때 쓰는 꾸밈. 로고 파일을 읽지 못하면 로고 없이 보낸다 (메일은 막지 않는다).
     * 부르는 쪽의 트랜잭션 밖에서 읽는다. 로고 읽기가 실패해도 안내 발송 기록이 함께 롤백되지 않는다.
     */
    @Transactional(propagation = Propagation.NOT_SUPPORTED)
    public MailBrand brand(UUID companyId) {
        return styles.findById(companyId).map(style -> {
            String color = style.getColor() == null ? MailBrand.DEFAULT_COLOR : style.getColor();
            if (style.getLogoFileId() == null) {
                return new MailBrand(color, null);
            }
            try {
                FileContent logo = files.read(companyId, style.getLogoFileId());
                return new MailBrand(color, new MailBrand.Logo(logo.bytes(), logo.info().contentType()));
            } catch (RuntimeException unreadable) {
                return new MailBrand(color, null);
            }
        }).orElse(MailBrand.BASIC);
    }

    /**
     * 설정 화면의 미리보기. 고르는 중인 색과 올린 로고로 다음 전형 안내 양식의 예시 메일을 만든다.
     *
     * 트랜잭션 없이 brand와 조회 메서드를 부른다. 로고를 못 읽어도 로고 없이 보여 준다.
     *
     * @param color 저장 전 색. null이면 저장한 색이다
     */
    public MailPreview preview(UUID companyId, String color) {
        MailBrand saved = brand(companyId);
        MailBrand brand = color == null ? saved : new MailBrand(normalize(color), saved.logo());
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

    private static String imageType(byte[] content) {
        if (startsWith(content, PNG)) {
            return "image/png";
        }
        if (startsWith(content, JPEG)) {
            return "image/jpeg";
        }
        throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_LOGO", "Only PNG or JPEG logos are allowed.");
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
                style.getLogoFileId() != null);
    }
}
