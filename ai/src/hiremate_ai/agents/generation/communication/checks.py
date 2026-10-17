"""모델이 쓴 안내 본문 검사. 코드로 고칠 수 있는 것은 고치고(tidy), 나머지는 다시 쓰게 할 이유를 찾는다(problems)."""

import re

MAX_CONTENT_LENGTH = 5000
"""backend NoticeEditRequest.content의 최대 길이."""

# 숫자와 단위 사이 공백. qwen3.5가 "1 차", "11 월 3 일"처럼 쓴다
_NUMBER_SPACE = re.compile(r"(\d)\s+(차|월|일|시|분|층|명|년|회|번째|시간)")
# 쉼표나 마침표 뒤에 바로 한글이 붙은 곳
_PUNCTUATION_SPACE = re.compile(r"([,.])(?=[가-힣])")
# 히라가나, 가타카나, 한자
_FOREIGN = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]+")
_VARIABLE = re.compile(r"\{[^{}]*\}")
_GREETING = re.compile(r"^\s*(안녕하세요|안녕하십니까)")
_CLOSINGS = {"감사합니다", "감사드립니다"}
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_DATE = re.compile(r"\d{1,4}\s*(?:년|월|일|시|분)")


def tidy(content: str) -> str:
    """띄어쓰기처럼 뜻이 바뀌지 않는 것만 코드로 고친다."""
    content = _NUMBER_SPACE.sub(r"\1\2", content)
    content = _PUNCTUATION_SPACE.sub(r"\1 ", content)
    return content.strip()


def problems(content: str, source: str) -> list[str]:
    """작성 규칙을 어긴 곳. 비어 있으면 통과다. source는 모델에게 준 정보로, 날짜를 지어냈는지 볼 때 쓴다."""
    found = []
    if not content:
        found.append("본문이 비어 있다")
    if len(content) > MAX_CONTENT_LENGTH:
        found.append(f"본문이 {MAX_CONTENT_LENGTH}자를 넘는다")
    if foreign := _FOREIGN.findall(content):
        found.append(f"한국어가 아닌 문자(한자, 일본어)를 썼다: {', '.join(foreign)}")
    if variables := _VARIABLE.findall(content):
        found.append(f"중괄호 변수를 썼다: {', '.join(variables)}")
    if _GREETING.match(content):
        found.append("인사말로 시작한다")
    if _last_sentence(content) in _CLOSINGS:
        found.append("맺음말로 끝난다")
    if invented := [date for date in _DATE.findall(content) if _compact(date) not in _compact(source)]:
        found.append(f"주어진 정보에 없는 날짜나 시각을 썼다: {', '.join(invented)}")
    return found


def _last_sentence(content: str) -> str:
    sentences = [sentence for sentence in _SENTENCE_END.split(content.strip()) if sentence]
    return sentences[-1].rstrip(".!?") if sentences else ""


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)
