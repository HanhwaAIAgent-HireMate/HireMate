import com.hiremate.file.PdfText;
import javax.imageio.ImageIO;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.rendering.PDFRenderer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.zip.ZipFile;
import tools.jackson.databind.json.JsonMapper;

/** 로컬 ZIP만 읽고 외부 모델·DB에는 전송하지 않는다. */
public class ParsePdfs {
    public static void main(String[] args) throws Exception {
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        Files.createDirectories(output);
        JsonMapper json = new JsonMapper();
        List<Map<String, Object>> documents = new ArrayList<>();
        Map<String, Applicant> applicants = new LinkedHashMap<>();
        try (ZipFile zip = new ZipFile(args[0], StandardCharsets.UTF_8)) {
            var entries = zip.entries();
            while (entries.hasMoreElements()) {
                var entry = entries.nextElement();
                if (entry.isDirectory() || !entry.getName().toLowerCase(Locale.ROOT).endsWith(".pdf")) {
                    continue;
                }
                Path relative = Path.of(entry.getName().replace('\\', '/')).normalize();
                Path target = output.resolve(relative).normalize();
                if (relative.isAbsolute() || !target.startsWith(output)) {
                    throw new IllegalArgumentException("Unsafe ZIP entry path");
                }
                if (entry.getSize() < 0 || entry.getSize() > 30_000_000) {
                    throw new IllegalArgumentException("PDF size limit exceeded");
                }
                byte[] bytes;
                try (var input = zip.getInputStream(entry)) {
                    bytes = input.readNBytes(30_000_001);
                }
                if (bytes.length > 30_000_000) {
                    throw new IllegalArgumentException("PDF size limit exceeded");
                }
                PdfText.Result parsed = PdfText.parse(bytes);
                Files.createDirectories(target.getParent());
                // 원본 경로를 보존하고 결과를 별도 파일로 쓴다. 원본 ZIP은 수정하지 않는다.
                Path report = target.resolveSibling(target.getFileName() + ".json");
                Map<String, Object> record = new LinkedHashMap<>();
                record.put("source", entry.getName());
                record.put("sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));
                record.put("pageCount", parsed.pageCount());
                record.put("reviewRequired", parsed.reviewRequired());
                record.put("issues", parsed.issues());
                record.put("pages", parsed.pages());
                record.put("text", parsed.text());
                Files.writeString(report, json.writerWithDefaultPrettyPrinter().writeValueAsString(record));
                Files.writeString(target.resolveSibling(target.getFileName() + ".txt"), parsed.text());
                if (parsed.pages().stream().anyMatch(page -> !page.issues().isEmpty())) {
                    try (var pdf = Loader.loadPDF(bytes)) {
                        PDFRenderer renderer = new PDFRenderer(pdf);
                        for (var page : parsed.pages()) {
                            if (!page.issues().isEmpty()) {
                                Path preview = target.resolveSibling(target.getFileName() + ".page-" + page.number() + ".png");
                                ImageIO.write(renderer.renderImageWithDPI(page.number() - 1, 110), "png", preview.toFile());
                            }
                        }
                    } catch (Exception error) {
                        System.err.println("Preview rendering failed: " + entry.getName());
                    }
                }
                String file = target.getFileName().toString();
                String type = documentType(file);
                record.remove("text");
                record.remove("pages");
                documents.add(record);
                if (!type.isEmpty() && file.matches("BE-\\d+_.*")) {
                    String id = file.substring(0, file.indexOf('_'));
                    String name = file.substring(file.indexOf('_') + 1, file.lastIndexOf('_'));
                    var applicant = applicants.computeIfAbsent(id, key -> new Applicant(id, name, new ArrayList<>()));
                    applicant.documents().add(Map.of("type", type, "fileName", file, "text", parsed.text(),
                            "reviewRequired", parsed.reviewRequired(), "source", entry.getName()));
                }
            }
        }
        Files.writeString(output.resolve("manifest.json"),
                json.writerWithDefaultPrettyPrinter().writeValueAsString(documents));
        Files.writeString(output.resolve("applicant-documents.json"),
                json.writerWithDefaultPrettyPrinter().writeValueAsString(applicants.values()));
        System.out.println("PDFs=" + documents.size() + ", applicants=" + applicants.size());
    }

    public record Applicant(String id, String name, List<Map<String, Object>> documents) {
    }

    private static String documentType(String file) {
        if (file.endsWith("_이력서.pdf")) {
            return "RESUME";
        }
        if (file.endsWith("_자기소개서.pdf")) {
            return "COVER_LETTER";
        }
        if (file.endsWith("_포트폴리오.pdf")) {
            return "PORTFOLIO";
        }
        return "";
    }
}
