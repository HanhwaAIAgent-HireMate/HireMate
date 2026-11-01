package com.hiremate.company;

import com.hiremate.company.MailStyleService.Fit;
import com.hiremate.file.FileContent;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회사 로고. 설정 › 회사 소개에서 한 번 올리면 안내 메일과 공고 포스터에 같이 쓴다.
 * 메일용은 메일 머리 크기로 줄이고({@link MailStyleService#changeLogo}), 포스터용은 포스터 로고 한도(500KB,
 * 400만 화소) 안으로 줄여 넘긴다({@link PosterBrandService#upload}). 포스터 브랜드 색은 포스터 로고를 올릴 때처럼
 * 로고의 대표 색으로 바뀌고, 메일 색은 바꾸지 않는다 (메일 꾸밈에서 로고 색을 골라 저장한다).
 */
@Service
public class CompanyLogoService {

    /** 포스터용으로 줄여 볼 크기. 용량이 500KB를 넘으면 다음 크기로 더 줄인다 (사진처럼 잘 안 줄어드는 그림). */
    private static final List<Fit> POSTER_FITS = List.of(new Fit(1600, 1600, 500 * 1024),
            new Fit(1000, 1000, 500 * 1024), new Fit(600, 600, 500 * 1024), new Fit(300, 300, 500 * 1024));

    private final MailStyleService mailStyles;
    private final PosterBrandService posterBrands;

    public CompanyLogoService(MailStyleService mailStyles, PosterBrandService posterBrands) {
        this.mailStyles = mailStyles;
        this.posterBrands = posterBrands;
    }

    /** 로고를 메일용과 포스터용으로 저장한다. 메일용 저장이 형식(PNG, JPEG)과 용량(5MB)을 먼저 확인한다. */
    @Transactional
    public void upload(UUID companyId, String name, byte[] content) {
        mailStyles.changeLogo(companyId, name, content);
        posterBrands.upload(companyId, name, posterSized(content));
    }

    @Transactional
    public void delete(UUID companyId) {
        mailStyles.deleteLogo(companyId);
        posterBrands.delete(companyId);
    }

    /** 설정 화면에 보여 줄 로고. 메일용으로 줄인 그림이다. */
    @Transactional(readOnly = true)
    public FileContent logo(UUID companyId) {
        return mailStyles.logo(companyId);
    }

    private static byte[] posterSized(byte[] content) {
        String type = MailStyleService.imageType(content);
        byte[] fitted = content;
        for (Fit fit : POSTER_FITS) {
            fitted = MailStyleService.shrink(content, type, fit);
            if (fitted.length <= fit.maxBytes()) {
                return fitted;
            }
        }
        return fitted;
    }
}
