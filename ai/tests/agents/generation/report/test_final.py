import httpx2
from openai import APIConnectionError

from hiremate_ai.agents.generation.report.bundle import Evidence, ReportBundle
from hiremate_ai.agents.generation.report.check import problems
from hiremate_ai.agents.generation.report.compose import compose_report
from hiremate_ai.agents.generation.report.fallback import fallback_spec
from hiremate_ai.agents.generation.report.final import _Draft, _Finalist, _Point
from hiremate_ai.agents.generation.report.spec import EvidenceBlock, TextBlock
from hiremate_ai.llm.fake import FakeLlm, LlmCall

from .test_compose import INTERVIEW, STAGE, final_bundle


def with_evidence() -> ReportBundle:
    """최종 합격자(A-0012 · A-0021)와 불합격자(A-0007)의 근거가 있는 최종 리포트 묶음."""

    def item(id_: str, number: str, stage: object, text: str) -> Evidence:
        return Evidence(id=id_, applicant=number, stage_id=stage, agent="application", text=text, source="이력서")

    evidence = [
        item("e-A-0012-Q-01", "A-0012", STAGE, "서버 개발 경력 5년이 확인돼요."),
        item("e-A-0012-iv", "A-0012", INTERVIEW, "면접에서 테스트 작성 경험을 설명했어요."),
        item("e-A-0021-Q-01", "A-0021", STAGE, "서버 개발 경력 4년이 확인돼요."),
        item("e-A-0007-Q-01", "A-0007", STAGE, "서버 개발 경력 3년이 확인돼요."),
    ]
    return final_bundle().model_copy(update={"evidence": evidence})


GOOD = _Draft(
    summary="지원 4명 중 최종 합격은 2명이에요. 다음 채용에서는 테스트 코드 경험을 서류에서 더 확인할 필요가 있어요.",
    finalists=[
        _Finalist(
            applicant="A-0012", keywords=["서버 개발 경력", "테스트 작성"], evidence=["e-A-0012-Q-01", "e-A-0012-iv"]
        ),
        _Finalist(applicant="A-0021", keywords=["서버 개발 경력"], evidence=["e-A-0021-Q-01"]),
    ],
    notable=[_Point(text="A-0012는 서류에서 부분이던 테스트 경험을 면접에서 설명했어요.", evidence=["e-A-0012-iv"])],
)


async def test_final_report_keeps_the_code_layout_and_adds_only_model_sentences() -> None:
    bundle = with_evidence()
    llm = FakeLlm(GOOD)

    composed = await compose_report(bundle, llm)

    # 모델은 문장 담당 한 번만 부른다. 그래프 · 인원 표는 코드 구성 그대로다
    assert [call.agent for call in llm.calls] == ["report-final"]
    code = fallback_spec(bundle)
    assert [b.type for b in code.all_blocks()] == [
        b.type for b in composed.spec.all_blocks() if not isinstance(b, EvidenceBlock | TextBlock)
    ]
    assert composed.spec.summary == GOOD.summary
    evidence = [b for b in composed.spec.all_blocks() if isinstance(b, EvidenceBlock)]
    assert [item.applicant for item in evidence[0].items] == ["A-0012", "A-0021"]
    notes = [b for b in composed.spec.all_blocks() if isinstance(b, TextBlock)]
    assert notes[0].evidence == ["e-A-0012-iv"]
    assert not composed.fallback
    assert "AI 문장 검사를 1번째에 통과" in composed.steps
    assert [p for p in problems(composed.spec, bundle) if "근거 부품" not in p] == []


async def test_final_sentences_that_break_the_rules_are_rewritten_then_dropped() -> None:
    bad = _Draft(
        # 순위 표현, 판정 코드, 최종 합격자가 아닌 지원자, 남의 근거 id
        summary="A-0012가 가장 우수해요.",
        finalists=[
            _Finalist(applicant="A-0012", keywords=["서버 개발 경력"], evidence=["e-A-0007-Q-01"]),
            _Finalist(applicant="A-0007", keywords=["서버 개발 경력"], evidence=["e-A-0007-Q-01"]),
            _Finalist(applicant="A-0021", keywords=["서버 개발 경력"], evidence=["e-A-0021-Q-01"]),
        ],
        notable=[_Point(text="A-0021은 PASS예요.", evidence=["e-A-0021-Q-01"])],
    )
    seen: list[str] = []

    def answer(call: LlmCall) -> _Draft:
        seen.append(call.user)
        return bad

    composed = await compose_report(with_evidence(), FakeLlm(answer, answer))

    assert "고칠 점" in seen[1] and "순위나 추천" in seen[1]
    # 요약은 코드가 쓴 인원 문장으로 남고, 통과한 항목만 들어간다
    assert "가장 우수" not in composed.spec.summary
    evidence = [b for b in composed.spec.all_blocks() if isinstance(b, EvidenceBlock)]
    assert [item.applicant for item in evidence[0].items] == ["A-0021"]
    # 판정 코드는 코드가 화면 말로 바꿔 통과시킨다
    notes = [b for b in composed.spec.all_blocks() if isinstance(b, TextBlock)]
    assert notes[0].text == "A-0021은 합격이에요."
    assert "검사에 걸린 AI 문장은 뺌" in composed.steps


async def test_final_report_is_records_only_when_the_model_server_fails() -> None:
    def down(call: LlmCall) -> _Draft:
        raise APIConnectionError(request=httpx2.Request("POST", "http://model.test"))

    bundle = with_evidence()
    composed = await compose_report(bundle, FakeLlm(down))

    assert composed.fallback
    assert composed.spec == fallback_spec(bundle)
    assert composed.steps[-1] == "AI 문장을 넣지 못해 기록만 담음"
