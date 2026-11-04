import re
from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest
from ncs_context import UNIT, FakeNcs
from pydantic import BaseModel

from hiremate_ai.agents.generation.interview import ncs as interview_ncs
from hiremate_ai.agents.generation.interview.agent import QuestionDraft, _DraftQuestion, generate_questions
from hiremate_ai.agents.generation.interview.ncs import NcsCheck, NcsVerdict
from hiremate_ai.agents.generation.interview.types import CitedQuestionDraft, InterviewQuestionDraft
from hiremate_ai.contract import (
    ApplicantDetail,
    CandidateAnalysis,
    Condition,
    Finding,
    InterviewerMemo,
    InterviewView,
    NcsUse,
    PostingContent,
)
from hiremate_ai.llm.fake import FakeLlm, LlmCall
from hiremate_ai.ncs_search.cite import NcsQuery
from hiremate_ai.ncs_search.types import NcsTask

SENTENCE = "하위 시스템 간의 연동 시, 안정적이고 안전하게 동작할 수 있는 배치 프로그램을 구현 한다"
BATCH = NcsTask(
    chunk_id="chunk:batch",
    duty_name="응용SW엔지니어링",
    unit_code=UNIT,
    unit_name="서버프로그램 구현",
    task_name="배치 프로그램 구현하기",
    sentences=[SENTENCE],
)
GOOD = (
    "하위 시스템끼리 연동하는 배치 프로그램이 중간에 실패한다면, "
    "다시 돌릴 때 같은 데이터가 두 번 처리되지 않게 하는 기준을 설명해 주세요."
)
ASSUMED = (
    "하위 시스템 연동 배치 프로그램을 구현하실 때, 실패한 작업을 다시 처리할 기준을 어떻게 정했는지 설명해 주세요."
)
OTHER = "결제 승인 API를 만들며 맡으신 부분과 테스트로 확인한 결과를 구체적으로 설명해 주세요."
FOCUS = "배치 처리 쪽 직무 지식 질문"


class Malformed(BaseModel):
    """모델이 형식에 맞지 않는 답을 냈을 때."""


@pytest.fixture(autouse=True)
def clear_search_cache() -> Iterator[None]:
    interview_ncs.clear_cache()
    yield
    interview_ncs.clear_cache()


@pytest.fixture
def analysis(sample_posting: PostingContent) -> CandidateAnalysis:
    required, rdbms = sample_posting.qualifications
    return CandidateAnalysis(
        conditions=[
            Condition(label="Java·Spring", met=False, requirement=required),
            Condition(label="RDBMS", met=True, requirement=rdbms),
        ],
        notable=[
            Finding(
                text="Spring Boot와 MySQL로 결제 승인 · 취소 API를 만들고 JUnit으로 테스트했습니다.", source="이력서"
            )
        ],
        checks=[],
        holds=[],
        criteria_version=None,
        criteria=[],
        summaries=[],
        highlights=[],
        agent="Application Agent",
        stub=False,
    )


@pytest.fixture
def interview() -> InterviewView:
    return InterviewView(application_id=uuid4(), schedule=None, questions=[], previous=[])


def model(
    *,
    sources: list[str] | None = None,
    questions: list[str] | None = None,
    checks: list[NcsCheck | BaseModel] | None = None,
) -> Callable[[LlmCall], BaseModel]:
    """호출 종류마다 답한다. 질문 쓰기는 ncs 블록이 있는 빈틈에 차례대로 sources · questions를 쓴다."""
    sources = list(sources or ["N1"])
    questions = list(questions or [GOOD])
    checks = list(checks or [])

    def reply(call: LlmCall) -> BaseModel:
        if call.output is NcsQuery:
            return NcsQuery(tasks=["배치 프로그램을 구현 한다"], units=[UNIT])
        if call.output is NcsCheck:
            if checks:
                return checks.pop(0)
            return NcsCheck(verdicts=[NcsVerdict(index=0, verdict="supports", assumes_experience=False)])
        drafts = []
        for gap_id in re.findall(r"gap_id: (G\d+)", call.user):
            if "[N1]" in call.user and gap_id == "G1":
                source = sources.pop(0) if len(sources) > 1 else sources[0]
                question = questions.pop(0) if len(questions) > 1 else questions[0]
                drafts.append(_DraftQuestion(gap_id=gap_id, question=question, purpose="재처리 기준", source_id=source))
            else:
                drafts.append(_DraftQuestion(gap_id=gap_id, question=OTHER, purpose="본인 역할"))
        return QuestionDraft(questions=drafts)

    return reply


def fake(reply: Callable[[LlmCall], BaseModel]) -> FakeLlm:
    """FakeLlm은 응답 하나를 한 번만 쓴다. 같은 응답 함수를 넉넉히 넣는다."""
    return FakeLlm(*([reply] * 20))


async def run(
    llm: FakeLlm,
    applicant: ApplicantDetail,
    posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
    *,
    ncs: NcsUse | None = None,
    reference: FakeNcs | None = None,
    memo: InterviewerMemo | None = None,
    count: int = 1,
) -> list[InterviewQuestionDraft]:
    drafts: list[InterviewQuestionDraft] = []
    if ncs is None:
        # ncs 인자를 전혀 주지 않는 기존 호출 그대로
        await generate_questions(
            llm,
            applicant=applicant,
            posting=posting,
            analysis=analysis,
            interview=interview,
            focus=FOCUS,
            question_count=count,
            drafts=drafts,
            memo=memo,
        )
        return drafts
    await generate_questions(
        llm,
        applicant=applicant,
        posting=posting,
        analysis=analysis,
        interview=interview,
        focus=FOCUS,
        question_count=count,
        drafts=drafts,
        memo=memo,
        ncs=ncs,
        ncs_reference=reference,
    )
    return drafts


def cited(drafts: list[InterviewQuestionDraft]) -> list[InterviewQuestionDraft]:
    return [draft for draft in drafts if isinstance(draft, CitedQuestionDraft) and draft.ncs_cited]


async def test_skip_prompts_are_unchanged(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    before, after = fake(model()), fake(model())
    reference = FakeNcs(found=[BATCH])
    applicant = sample_applicants["이도윤"]

    plain = await run(before, applicant, sample_posting, analysis, interview, count=2)
    skipped = await run(after, applicant, sample_posting, analysis, interview, ncs="SKIP", reference=reference, count=2)

    assert [(call.system, call.user) for call in after.calls] == [(call.system, call.user) for call in before.calls]
    assert reference.searches == []
    assert skipped == plain


async def test_skip_drafts_are_plain(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    drafts = await run(
        fake(model()), sample_applicants["이도윤"], sample_posting, analysis, interview, ncs="SKIP", count=2
    )

    assert drafts and all(type(draft) is InterviewQuestionDraft for draft in drafts)


async def test_helpful_cites_ncs_in_reason(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    reference = FakeNcs(found=[BATCH])
    drafts = await run(
        fake(model()),
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="HELPFUL",
        reference=reference,
    )

    [question] = cited(drafts)
    assert question.text == GOOD
    assert question.reason is not None
    assert "출처: NCS 응용SW엔지니어링 › 서버프로그램 구현 › 배치 프로그램 구현하기" in question.reason
    assert f"원문: {SENTENCE}" in question.reason
    assert all(not getattr(draft, "ncs_cited", False) for draft in drafts if draft.text != GOOD)
    assert reference.searches[0][0] == FOCUS


async def test_unknown_ncs_number_retries(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    llm = fake(model(sources=["N9", "N1"]))
    drafts = await run(
        llm,
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="HELPFUL",
        reference=FakeNcs(found=[BATCH]),
    )

    writes = [call for call in llm.calls if call.output is QuestionDraft]
    assert len(writes) == 2 and "NCS 번호는 N1 중 하나" in writes[1].user
    assert [draft.text for draft in cited(drafts)] == [GOOD]


async def test_ncs_number_in_question_is_rejected(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    llm = fake(model(questions=[GOOD.replace("기준을", "기준(N1)을"), GOOD]))
    drafts = await run(
        llm,
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="HELPFUL",
        reference=FakeNcs(found=[BATCH]),
    )

    writes = [call for call in llm.calls if call.output is QuestionDraft]
    assert len(writes) == 2 and "질문에 NCS 번호를 쓰지 않는다" in writes[1].user
    assert all("N1" not in draft.text for draft in drafts)


async def test_unrelated_drops_citation_keeps_question(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    unrelated = NcsCheck(verdicts=[NcsVerdict(index=0, verdict="unrelated", assumes_experience=False)])
    drafts = await run(
        fake(model(checks=[unrelated])),
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="HELPFUL",
        reference=FakeNcs(found=[BATCH]),
    )

    assert GOOD in [draft.text for draft in drafts]
    assert cited(drafts) == []
    assert all("출처: NCS" not in (draft.reason or "") for draft in drafts)


async def test_assumed_experience_is_rewritten(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    assumed = NcsCheck(verdicts=[NcsVerdict(index=0, verdict="supports", assumes_experience=True)])
    llm = fake(model(questions=[ASSUMED, GOOD], checks=[assumed]))
    drafts = await run(
        llm,
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="HELPFUL",
        reference=FakeNcs(found=[BATCH]),
    )

    writes = [call for call in llm.calls if call.output is QuestionDraft]
    assert len(writes) == 2 and "그 일을 했다고 전제하지 않고" in writes[1].user
    assert [draft.text for draft in cited(drafts)] == [GOOD]
    assert ASSUMED not in [draft.text for draft in drafts]


async def test_check_failure_drops_all_citations(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    """판정을 받지 못한 NCS 질문은 경험 전제를 확인하지 못했으므로 남기지 않는다. 다시 써도 안 되면 기본 질문이다."""
    llm = fake(model(checks=[Malformed(), Malformed()]))
    drafts = await run(
        llm,
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="HELPFUL",
        reference=FakeNcs(found=[BATCH]),
    )

    assert drafts and cited(drafts) == []
    assert GOOD not in [draft.text for draft in drafts]
    assert all("출처: NCS" not in (draft.reason or "") for draft in drafts)
    writes = [call for call in llm.calls if call.output is QuestionDraft]
    assert len(writes) == 2 and "출처 판정을 마치지 못해" in writes[1].user


async def test_job_name_is_part_of_search_reuse(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    """주요 업무가 같아도 직무가 다른 공고는 검색을 따로 한다."""
    reference = FakeNcs(found=[BATCH])
    llm = fake(model())
    other = sample_posting.model_copy(update={"job_category": "데이터 엔지니어"})
    for posting in (sample_posting, other):
        await run(llm, sample_applicants["이도윤"], posting, analysis, interview, ncs="HELPFUL", reference=reference)

    assert len(reference.searches) == 2


def test_expired_searches_are_dropped(monkeypatch: pytest.MonkeyPatch, sample_posting: PostingContent) -> None:
    """기한이 지난 검색 기억은 새로 기억할 때 지운다."""
    clock = iter([0.0, interview_ncs.CACHE_SECONDS + 1])
    monkeypatch.setattr(interview_ncs, "_now", lambda: next(clock))
    interview_ncs.remember(("첫 요청", "직무", ()), None)
    interview_ncs.remember(("둘째 요청", "직무", ()), None)

    assert interview_ncs.cached_keys() == [("둘째 요청", "직무", ())]


async def test_requested_not_found_has_no_cited(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    drafts = await run(
        fake(model()),
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="REQUESTED",
        reference=FakeNcs(found=[]),
    )

    assert drafts and cited(drafts) == []


async def test_helpful_unavailable_is_silent(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    drafts = await run(
        fake(model()),
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="HELPFUL",
        reference=FakeNcs(unavailable=True),
    )

    assert drafts and cited(drafts) == []


async def test_same_focus_reuses_search(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    reference = FakeNcs(found=[BATCH])
    llm = fake(model())
    for name in ("이도윤", "정유민"):
        await run(llm, sample_applicants[name], sample_posting, analysis, interview, ncs="HELPFUL", reference=reference)

    assert len(reference.searches) == 1
    assert len([call for call in llm.calls if call.output is NcsQuery]) == 1
    assert len([call for call in llm.calls if call.output is NcsCheck]) == 2


async def test_memo_request_ignores_ncs(
    sample_applicants: dict[str, ApplicantDetail],
    sample_posting: PostingContent,
    analysis: CandidateAnalysis,
    interview: InterviewView,
) -> None:
    reference = FakeNcs(found=[BATCH])
    memo = InterviewerMemo(stage_id=uuid4(), stage_name="1차 면접", text="리더 역할 확인")

    await run(
        FakeLlm(),
        sample_applicants["이도윤"],
        sample_posting,
        analysis,
        interview,
        ncs="REQUESTED",
        reference=reference,
        memo=memo,
    )

    assert reference.searches == []
