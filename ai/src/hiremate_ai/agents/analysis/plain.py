"""프로필 항목 문장의 말투를 평어(~다)로 맞춘다.

분석 Agent마다 모델이 쓰는 문장의 끝이 '~했습니다', '~했어요', '~하였다'로 달라 프로필 탭에서 섞여 보였다.
프롬프트로 평어를 요청하고, 남은 존댓말 끝은 이 함수가 바꾼다.
'~해요' · '~합니다'는 동사면 '~한다'(확인해요 → 확인한다), 형용사면 '~하다'(필요해요 → 필요하다)라서
평가 문장에 자주 나오는 형용사(_ADJECTIVE)만 '~하다'로, 나머지는 '~한다'로 바꾼다.
"""

import re

# 문장 끝(마침표 · 느낌표 · 물음표 앞이나 글 끝)의 존댓말 어미
_ENDING = re.compile(r"([가-힣])(습니다|어요|아요|이에요|예요|입니다)(?=[.!?]|\s*$)")
_HA = re.compile(r"([가-힣]+)(해요|합니다)(?=[.!?]|\s*$)")
_PLEASE = re.compile(r"(\s?)주세요(?=[.!?]|\s*$)")
# '~하다'로 끝나는 형용사. 동사('개발하다', '확인하다')는 '~한다'가 된다
_ADJECTIVE = re.compile(
    r"(필요|가능|불가능|부족|충분|불충분|명확|불명확|분명|불분명|확실|불확실|정확|부정확|적절|부적절|미흡|우수|"
    r"원활|유사|동일|능숙|익숙|미숙|모호|다양|풍부|탁월|중요|타당|일관|비슷|꼼꼼|적합|부적합)$"
)


def plain(text: str) -> str:
    """문장마다 끝의 존댓말을 평어로 바꾼다. 예: '개발했습니다.' → '개발했다.', '없어요' → '없다'."""
    text = _PLEASE.sub(r"\1줘야 한다", text.strip())  # '확인해 주세요' → '확인해 줘야 한다'
    return _ENDING.sub(_replace, _HA.sub(_replace_ha, text))


def _replace_ha(match: re.Match[str]) -> str:
    word = match.group(1)
    return f"{word}하다" if _ADJECTIVE.search(word) else f"{word}한다"


def _replace(match: re.Match[str]) -> str:
    head, ending = match.group(1), match.group(2)
    if ending in ("이에요", "예요", "입니다"):
        return f"{head}이다"
    if ending == "습니다":
        return f"{head}다"
    # '어요' · '아요'는 받침 있는 말(있어요, 했어요, 좋아요)만 '다'로 바꾼다
    # '봐요' · '보여요'처럼 줄어든 말은 그대로 둔다
    return f"{head}다" if _has_final(head) else match.group(0)


def _has_final(syllable: str) -> bool:
    return (ord(syllable) - 0xAC00) % 28 != 0
