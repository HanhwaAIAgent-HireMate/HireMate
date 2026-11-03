"""평가 채점 규칙 검사. 모델 없이 돈다. 채점이 틀리면 평가 숫자가 틀리므로 일부러 틀린 리포트로 확인한다."""

from hiremate_ai.agents.generation.report.compose import ComposedReport
from hiremate_ai.agents.generation.report.explain import DistributionNote
from hiremate_ai.agents.generation.report.fallback import fallback_spec
from hiremate_ai.agents.generation.report.spec import ReportSpec, Split

from .dataset import BY_NAME, bundle, cases, distribution, expected_splits
from .scoring import chart_numbers, plain_endings, score_distribution, score_report, summarize, verdict_claims

CASES = {case.id: case for case in cases()}


def composed(case_id: str, spec: ReportSpec, steps: list[str] | None = None) -> ComposedReport:
    case = CASES[case_id]
    return ComposedReport(
        spec=spec, skills=[], fallback=False, bundle=bundle(case), steps=steps or ["설계서 검사 1번째에 통과"]
    )


def number(name: str) -> str:
    return str(BY_NAME[name]["number"])


def test_dataset_cases_cover_every_kind_and_known_splits() -> None:
    assert {case.kind for case in CASES.values()} == {"COMPARE", "STAGE", "DISTRIBUTION"}
    assert expected_splits(CASES["C2"].targets) == {}
    # 자격요건 4/5인 3명은 각자 못 채운 항목이 갈린다
    assert {"Q-03", "Q-04", "Q-05"} <= set(expected_splits(CASES["C3"].targets))
    facts = distribution(10)
    assert (facts.above_line, facts.target) == (26, 10)
    assert facts.cut is not None and facts.cut["value"] == 6
    assert distribution(30).cut is None


def test_verdict_claims_pair_each_applicant_with_its_word() -> None:
    a, b, c = number("양시우"), number("권나연"), number("남궁현")
    text = f"{a}는 충족, {b}와 {c}는 미충족이에요. {a}만 부분 충족이 아니에요."
    assert verdict_claims(text) == [(a, "MET"), (b, "NOT_MET"), (c, "NOT_MET"), (a, "PARTIAL")]
    assert verdict_claims(f"{a}는 확인 필요예요.") == [(a, "UNKNOWN")]


def test_plain_endings_are_caught_but_haeyo_and_formal_are_not() -> None:
    assert plain_endings("판정이 갈렸다. 근거가 있어요.") == ["판정이 갈렸다."]
    assert plain_endings("충족했습니다.") == []  # 합니다체는 check가 따로 잡는다
    assert plain_endings("모두 충족이에요.") == []


def test_report_score_counts_split_hits_and_wrong_verdict_words() -> None:
    case = CASES["C3"]
    expected = expected_splits(case.targets)
    a = number("양시우")
    spec = fallback_spec(bundle(case)).model_copy(
        update={
            "splits": [
                # 양시우 Q-05는 미충족인데 충족이라고 쓴 문장: 판정 표현이 틀렸다
                Split(key="document.criterion.Q-05", text=f"{a}는 충족이에요.", evidence=[f"e-{a}-Q-05"]),
                # 근거 id가 다른 항목의 것이다: 근거 연결이 틀렸다
                Split(key="document.criterion.Q-04", text=f"{a}는 충족이에요.", evidence=[f"e-{a}-Q-03"]),
            ]
        }
    )
    score = score_report(case, bundle(case), composed("C3", spec), run=1)
    assert score.split_hit == 2
    # 갈린 항목은 7개지만 화면은 MAX_SPLITS(6)개까지라 6개 기준으로 놓친 수를 세고 넘친 1개는 따로 센다
    assert len(expected) == 7
    assert (score.split_missed, score.split_hidden) == (4, 1)
    assert (score.verdict_claims, score.verdict_hits) == (2, 1)
    # 기본 구성의 근거 부품은 모두 맞게 이어져 있고, 틀린 연결은 위 하나뿐이다
    assert score.links - score.links_ok == 1
    assert score.first_pass and not score.fallback


def test_report_score_flags_forbidden_words_and_plain_endings() -> None:
    case = CASES["C8"]
    spec = fallback_spec(bundle(case)).model_copy(update={"summary": "한예린은 모든 우대사항을 충족했다."})
    score = score_report(case, bundle(case), composed("C8", spec), run=1)
    assert any("금지 표현 '모든 우대사항을 충족'" in v for v in score.violations)
    assert any("평어" in v for v in score.violations)


def test_distribution_score_counts_numbers_from_another_chart_as_a_link_miss() -> None:
    case = CASES["D1"]
    facts = distribution(10)
    allowed = chart_numbers(facts)
    assert "26" in allowed["funnel"] and "26" not in allowed["careers"]
    note = DistributionNote(
        lines=["필수 조건을 모두 충족한 26명이 목표 10명보다 많아요."],
        # 경력 차트 문장에 깔때기 차트의 숫자(26명)를 섞어 쓴 문장
        charts={"careers": "필수 조건 충족자 26명은 경력 구간마다 고르게 있어요.", "funnel": "목표보다 16명 많아요."},
    )
    score = score_distribution(case, facts, note, run=1)
    # 자료에 있는 숫자라 위반은 아니지만, 그 차트의 숫자가 아니라 근거 연결을 깎는다
    assert not any(v.startswith("차트 careers") for v in score.violations)
    assert any(m.startswith("차트 careers") and "26" in m for m in score.misplaced)
    assert not any(m.startswith("차트 funnel") for m in score.misplaced)
    assert any("해설이 빠졌다" in v for v in score.violations)
    linkage = summarize([score])["linkage"]
    assert linkage is not None and linkage < 1.0


def test_metric_without_any_measured_sentence_is_none_not_perfect() -> None:
    # 판정 표현을 하나도 못 찾았으면 100%가 아니라 '측정 안 됨'이다
    case = CASES["C2"]
    score = score_report(case, bundle(case), composed("C2", fallback_spec(bundle(case))), run=1)
    assert score.verdict_claims == 0
    assert summarize([score])["verdict_accuracy"] is None


def test_distribution_score_rejects_a_number_no_chart_has() -> None:
    facts = distribution(10)
    note = DistributionNote(lines=["확인 필요가 194명이에요."], charts={})
    score = score_distribution(CASES["D1"], facts, note, run=1)
    assert any("194" in v for v in score.violations)


def test_distribution_score_accepts_the_re_review_group_size() -> None:
    # 다시 볼 지원자 인원은 차트 밖 칸에 나오지만 자료에 있는 숫자다
    facts = distribution(30)
    size = facts.groups[0].size
    note = DistributionNote(lines=[f"다시 볼 지원자 {size}명의 필수 조건 판정을 먼저 확인해요."], charts={})
    score = score_distribution(CASES["D2"], facts, note, run=1)
    assert not any("자료에 없는 숫자" in v for v in score.violations)
