// 블라인드 채용에서 쓰지 않는 학력 · 출신 학교 조건. backend BlindTerms, ai guardrails의 _BLIND_ATTRIBUTE와 같은 낱말이다.
// 직무와 관련된 전공, 자격, 경력은 막지 않는다
const SCHOOL_ORIGIN =
  '(?:(?!여)[가-힣A-Za-z]대|SKY|대학교?|대학원|학교|고등학교|고교)\\s*출신|출신\\s*(?:학교|대학교?|교)'
const BLIND_TERMS = new RegExp(
  `${SCHOOL_ORIGIN}|(?:[가-힣A-Za-z]대|대학교?|대학원)\\s*(?:나온|졸업)|대학교|학교명|대학명` +
    '|학력|학벌|학위|학사|석사|박사|대졸|고졸|전문대|명문대|지방대|인서울|학점' +
    '|(?<![A-Za-z])(?:SKY|GPA)(?![A-Za-z])',
)

/** 학력 · 출신 학교 조건이 들어간 줄의 번호(1부터). 블라인드 채용 공고는 이 줄이 있으면 게시할 수 없다 */
export function blindLineNumbers(lines: string[]): number[] {
  return lines.flatMap((line, index) => (BLIND_TERMS.test(line) ? [index + 1] : []))
}
