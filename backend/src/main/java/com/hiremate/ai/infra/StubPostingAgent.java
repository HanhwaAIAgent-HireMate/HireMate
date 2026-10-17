package com.hiremate.ai.infra;

import com.hiremate.ai.application.AiAgent;
import com.hiremate.ai.application.AiMode;
import com.hiremate.ai.application.PostingAgent;
import com.hiremate.posting.DocumentType;
import com.hiremate.posting.PostingContent;
import com.hiremate.posting.PostingDraftContext;
import com.hiremate.posting.PostingSuggestion;
import com.hiremate.recruit.RecruitmentStatus;
import com.hiremate.recruit.StageDraft;
import com.hiremate.recruit.StageType;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

/**
 * 개발용 Posting Agent. ai 서버가 붙기 전까지 규칙으로 수정 요청을 처리한다.
 * 전형 절차 말하기 · 빼기, 필수 제출 서류, 각 칸에 줄 더하기, 채용명 · 고용 형태 · 경력 · 근무지를 다룬다.
 */
@Component
@ConditionalOnAiMode(agent = AiAgent.POSTING, mode = AiMode.STUB)
class StubPostingAgent implements PostingAgent {

    private static final Pattern STAGE_PLAN = Pattern.compile("전형(?:은|을|는)?\\s*(.+?)\\s*순(?:서)?(?:으로|로)?");
    private static final Pattern STAGE_REMOVE = Pattern.compile("(.+?)(?:은|는|을|를)?\\s*빼");
    private static final Pattern SECTION_ADD = Pattern.compile("(주요 업무|자격 요건|우대 사항)에\\s*(.+?)(?:을|를)\\s");
    private static final Pattern TITLE = Pattern.compile("채용명(?:은|을)?\\s*(.+?)(?:으로|로)\\s");
    private static final Pattern LOCATION = Pattern.compile("근무지(?:는|를)?\\s*(.+?)(?:으로|로)\\s");
    private static final Pattern CAREER = Pattern.compile("(경력\\s*\\d+\\s*년\\s*이상|신입|경력 무관)");
    private static final Pattern EMPLOYMENT = Pattern.compile("(정규직|계약직|인턴)");
    private static final Map<String, String> SECTION_FIELDS =
            Map.of("주요 업무", "duties", "자격 요건", "qualifications", "우대 사항", "preferred");

    @Override
    public Result revise(PostingDraftContext posting, String writingStyle, String request) {
        String message = request.trim() + " ";
        boolean locked = posting.status() != RecruitmentStatus.DRAFT;

        if (message.contains("필수") && (message.contains("포트폴리오") || message.contains("자격증"))) {
            return locked ? lockedReply() : requiredDocuments(posting, message);
        }
        Matcher plan = STAGE_PLAN.matcher(message);
        if (plan.find() && plan.group(1).contains(",")) {
            return locked ? lockedReply() : stagePlan(posting, plan.group(1));
        }
        Matcher remove = STAGE_REMOVE.matcher(message);
        if (remove.find()) {
            Optional<StageDraft> target = posting.stages().stream()
                    .filter(stage -> remove.group(1).contains(stage.name()))
                    .findFirst();
            if (target.isPresent()) {
                if (locked) {
                    return lockedReply();
                }
                List<StageDraft> stages = new ArrayList<>(posting.stages());
                stages.remove(target.get());
                return new Result("전형 절차에서 " + target.get().name() + "을(를) 뺐어요.",
                        new PostingSuggestion(posting.content(), stages, null, List.of("stages")));
            }
        }
        Matcher section = SECTION_ADD.matcher(message);
        if (section.find()) {
            return addLine(posting.content(), section.group(1), section.group(2));
        }
        PostingContent content = posting.content();
        List<String> changed = new ArrayList<>();
        Matcher title = TITLE.matcher(message);
        String newTitle = title.find() ? title.group(1).trim() : content.title();
        if (!newTitle.equals(content.title())) {
            changed.add("title");
        }
        Matcher location = LOCATION.matcher(message);
        String newLocation = location.find() ? location.group(1).trim() : content.location();
        if (!newLocation.equals(content.location())) {
            changed.add("location");
        }
        Matcher career = CAREER.matcher(message);
        String newCareer = career.find() ? career.group(1).replaceAll("\\s+", " ") : content.career();
        if (!newCareer.equals(content.career())) {
            changed.add("career");
        }
        Matcher employment = EMPLOYMENT.matcher(message);
        String newEmployment = employment.find() ? employment.group(1) : content.employmentType();
        if (!newEmployment.equals(content.employmentType())) {
            changed.add("employmentType");
        }
        if (!changed.isEmpty()) {
            PostingContent revised = new PostingContent(newTitle, content.jobCategory(), newEmployment, newCareer,
                    newLocation, content.intro(), content.duties(), content.qualifications(), content.preferred(),
                    content.benefits());
            return new Result("요청한 내용으로 공고 정보를 고쳤어요.",
                    new PostingSuggestion(revised, null, null, changed));
        }
        return new Result("지금은 개발용 AI라 전형 절차(\"서류, 코딩테스트, 1차 면접 순으로\"), 필수 제출 서류, "
                + "주요 업무 · 자격 요건 · 우대 사항에 내용 더하기, 채용명 · 고용 형태 · 경력 · 근무지 요청을 처리해요.", null);
    }

    private static Result stagePlan(PostingDraftContext posting, String spoken) {
        List<StageDraft> stages = new ArrayList<>();
        List<String> unclear = new ArrayList<>();
        for (String raw : spoken.split("[,，、]|\\s그리고\\s")) {
            String name = raw.trim().replaceAll("^(그리고|그다음|다음)\\s*", "");
            if (name.isEmpty()) {
                continue;
            }
            Optional<StageType> type = classify(name);
            if (type.isEmpty()) {
                unclear.add(name);
            } else {
                stages.add(new StageDraft(name.equals("서류") ? "서류 전형" : name, type.get()));
            }
        }
        if (!unclear.isEmpty()) {
            return new Result("'" + String.join("', '", unclear) + "'은(는) 서류 · 평가 · 면접 중 어떤 전형인가요?", null);
        }
        Map<StageType, Long> counts = stages.stream()
                .collect(Collectors.groupingBy(StageDraft::type, Collectors.counting()));
        String summary = List.of(StageType.DOCUMENT, StageType.ASSESSMENT, StageType.INTERVIEW).stream()
                .filter(counts::containsKey)
                .map(type -> label(type) + " " + counts.get(type) + "개")
                .collect(Collectors.joining(", "));
        return new Result("전형 절차를 정리했어요. " + summary + "로 봤어요.",
                new PostingSuggestion(posting.content(), stages, null, List.of("stages")));
    }

    /** 전형 이름으로 종류를 알아듣는다. 애매하면 추측하지 않는다. */
    static Optional<StageType> classify(String name) {
        if (name.contains("면접") || name.contains("인터뷰")) {
            return Optional.of(StageType.INTERVIEW);
        }
        if (name.contains("서류")) {
            return Optional.of(StageType.DOCUMENT);
        }
        for (String keyword : List.of("평가", "테스트", "검사", "과제", "시험", "코딩", "역량", "적성")) {
            if (name.contains(keyword)) {
                return Optional.of(StageType.ASSESSMENT);
            }
        }
        return Optional.empty();
    }

    private static Result requiredDocuments(PostingDraftContext posting, String message) {
        Set<DocumentType> extras = EnumSet.noneOf(DocumentType.class);
        extras.addAll(posting.requiredExtras());
        boolean optional = message.contains("선택") || message.contains("빼") || message.contains("필수 아");
        List<String> names = new ArrayList<>();
        for (DocumentType type : List.of(DocumentType.PORTFOLIO, DocumentType.CERTIFICATE)) {
            if (message.contains(type.label())) {
                names.add(type.label());
                if (optional) {
                    extras.remove(type);
                } else {
                    extras.add(type);
                }
            }
        }
        String reply = optional
                ? String.join(", ", names) + "을(를) 선택 제출로 바꿨어요."
                : "필수 제출 서류에 " + String.join(", ", names) + "을(를) 넣었어요.";
        return new Result(reply,
                new PostingSuggestion(posting.content(), null, extras, List.of("requiredDocuments")));
    }

    private static Result addLine(PostingContent content, String section, String topic) {
        String field = SECTION_FIELDS.get(section);
        String trimmed = topic.trim();
        String line = switch (field) {
            case "duties" -> trimmed.endsWith("업무") ? trimmed : trimmed + " 업무";
            default -> trimmed.endsWith("경험") ? trimmed + "이 있으신 분" : trimmed + " 경험이 있으신 분";
        };
        List<String> duties = new ArrayList<>(content.duties());
        List<String> qualifications = new ArrayList<>(content.qualifications());
        List<String> preferred = new ArrayList<>(content.preferred());
        switch (field) {
            case "duties" -> duties.add(line);
            case "qualifications" -> qualifications.add(line);
            default -> preferred.add(line);
        }
        PostingContent revised = new PostingContent(content.title(), content.jobCategory(), content.employmentType(),
                content.career(), content.location(), content.intro(), duties, qualifications, preferred,
                content.benefits());
        return new Result(section + "에 \"" + line + "\" 줄을 더했어요.",
                new PostingSuggestion(revised, null, null, List.of(field)));
    }

    private static Result lockedReply() {
        return new Result("게시한 공고는 전형 절차와 필수 제출 서류를 바꿀 수 없어요. 본문 내용만 고칠 수 있어요.", null);
    }

    private static String label(StageType type) {
        return switch (type) {
            case DOCUMENT -> "서류";
            case ASSESSMENT -> "평가";
            case INTERVIEW -> "면접";
        };
    }
}
