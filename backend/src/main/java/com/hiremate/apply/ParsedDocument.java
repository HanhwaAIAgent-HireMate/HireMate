package com.hiremate.apply;

import com.hiremate.file.PdfText;
import com.hiremate.posting.BlindMask;
import java.util.ArrayList;
import java.util.List;

/** 페이지와 파서의 재검토 사유를 보존한 블라인드 원문. */
public record ParsedDocument(int pageCount, List<PdfText.Page> pages, List<String> issues,
                             List<DocumentSource> sources) {
    public ParsedDocument {
        pages = List.copyOf(pages);
        issues = List.copyOf(issues);
        sources = List.copyOf(sources);
    }

    public static ParsedDocument from(PdfText.Result result, boolean blind) {
        List<PdfText.Page> pages = new ArrayList<>();
        List<DocumentSource> sources = new ArrayList<>();
        for (PdfText.Page page : result.pages()) {
            String text = blind ? BlindMask.mask(page.text()) : page.text();
            pages.add(new PdfText.Page(page.number(), text, page.issues()));
            text.lines().filter(line -> !line.isBlank()).forEach(line -> sources.add(
                    new DocumentSource("s" + (sources.size() + 1), page.number(), line)));
        }
        return new ParsedDocument(result.pageCount(), pages, result.issues(), sources);
    }
}
