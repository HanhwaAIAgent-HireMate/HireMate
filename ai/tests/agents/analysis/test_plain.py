"""프로필 항목 문장을 평어(~다)로 바꾸는 plain()을 검사한다."""

import pytest

from hiremate_ai.agents.analysis.plain import plain


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 습니다 · 어요 · 아요
        ("결제 API를 개발했습니다.", "결제 API를 개발했다."),
        ("응답 시간을 줄였어요.", "응답 시간을 줄였다."),
        ("수리능력 점수가 없어요", "수리능력 점수가 없다"),
        ("결과가 좋아요.", "결과가 좋다."),
        # 이에요 · 예요 · 입니다
        ("핵심 역할이에요.", "핵심 역할이다."),
        ("팀 리더예요.", "팀 리더이다."),
        ("3년 경력입니다.", "3년 경력이다."),
        # 해요 · 합니다: 형용사는 '~하다', 동사는 '~한다'
        ("추가 확인이 필요해요.", "추가 확인이 필요하다."),
        ("설명이 명확합니다.", "설명이 명확하다."),
        ("배포 파이프라인을 설계해요.", "배포 파이프라인을 설계한다."),
        ("면접에서 확인합니다.", "면접에서 확인한다."),
        # 주세요
        ("원본 PDF를 확인해 주세요.", "원본 PDF를 확인해 줘야 한다."),
        # 여러 문장은 문장마다 바꾼다
        ("평가하지 않았어요. 원본을 확인해 주세요.", "평가하지 않았다. 원본을 확인해 줘야 한다."),
    ],
)
def test_plain_turns_polite_endings_into_plain(text: str, expected: str) -> None:
    assert plain(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "결제 API를 개발했다.",  # 이미 평어
        "Java · Spring 기반 결제 서비스 운영",  # 명사로 끝남
        "실무 역량이 있어 보여요",  # '보여요'처럼 줄어든 말은 바꾸지 않는다
        "습니다 라는 말이 문장 가운데에 있어도 그대로 둔다.",  # 문장 끝이 아니면 그대로
    ],
)
def test_plain_keeps_text_without_polite_ending(text: str) -> None:
    assert plain(text) == text


def test_plain_strips_spaces() -> None:
    assert plain("  응답 시간을 줄였어요.  ") == "응답 시간을 줄였다."
