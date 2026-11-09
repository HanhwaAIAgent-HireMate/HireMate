/**
 * 지원자 예시 사진 (QA · 시연용). 실제 지원서에는 사진을 받지 않아, 이름으로 성별을 짐작해 예시 사진 한 장을 붙인다.
 * 남자면 man_1~4, 여자면 woman_1~4 중 지원자마다 정해진 한 장이다 (같은 지원자는 늘 같은 사진).
 * 사진은 지금 frontend/public/applicants에 있고, S3에 올린 뒤에는 VITE_APPLICANT_PHOTO_BASE에 그 주소를 주면 된다.
 * 성별을 짐작하지 못한 이름(지안 · 지원처럼 남녀 모두 쓰는 이름)은 지원자마다 남자 · 여자를 번갈아 정해 사진을 붙인다.
 * 블라인드 채용으로 이름을 가린 지원자(예: 12번 지원자)는 사진 없이 아이콘을 쓴다.
 */
const PHOTO_BASE: string =
  (import.meta.env.VITE_APPLICANT_PHOTO_BASE as string | undefined) ?? '/applicants'
const PHOTOS_PER_GENDER = 4

export type Gender = 'man' | 'woman'

// 자주 쓰는 이름 (성 뺀 이름). 남녀 모두 쓰는 이름(지원 · 서진 · 지안 · 하늘 등)은 넣지 않는다 (유진은 여자 쪽으로 본다)
const WOMAN_NAMES = new Set(
  (
    '서연 서윤 지우 서현 민서 하은 하윤 윤서 지유 지민 채원 수아 지아 지윤 은서 다은 예은 수빈 소율 예린 하린 ' +
    '유나 소희 세영 은영 지수 시은 민지 예진 다인 채은 나연 가은 서아 아린 은지 혜원 수연 지혜 유리 소연 ' +
    '나래 연주 다현 유진 하율 채윤 예서 서영 지은 미영 은비 다연 연서 소은 나은 예나 지현 수진 혜진 미진 은영 보람 슬기'
  ).split(' '),
)
const MAN_NAMES = new Set(
  (
    '민준 서준 도윤 예준 시우 하준 주원 지호 지후 준우 준서 도현 건우 현우 우진 선우 유준 정우 승우 승현 ' +
    '시윤 준혁 은우 지훈 민재 태윤 기현 승민 민혁 준호 태현 동욱 승호 민성 성민 재원 재현 동현 상현 ' +
    '시후 재윤 현준 진우 태민 민우 정민 성훈 영호 대현 종현 재훈 형준 경민 세훈 준영 윤호 현수 영민 지성 태양 이준'
  ).split(' '),
)
// 목록에 없을 때 이름 끝 글자로 짐작한다
const WOMAN_ENDINGS = new Set('아 은 연 희 린 나 미 혜 경 숙 정 영 비 리 솔 별 슬 람 랑'.split(' '))
const MAN_ENDINGS = new Set(
  '준 우 호 훈 혁 민 재 석 철 규 성 환 욱 태 진 수 식 용 남 범 웅 찬 빈'.split(' '),
)

/** 이름으로 성별을 짐작한다. 블라인드로 가린 이름이나 짐작할 수 없는 이름은 null이다 */
export function guessGender(name: string): Gender | null {
  const trimmed = name.trim()
  if (!/^[가-힣]{2,4}$/.test(trimmed)) return null
  // 두 글자 성(남궁 · 황보 · 제갈 · 선우 · 독고 · 사공)은 성을 두 글자로 뗀다
  const given =
    /^(남궁|황보|제갈|선우|독고|사공)/.test(trimmed) && trimmed.length === 4
      ? trimmed.slice(2)
      : trimmed.slice(1)
  if (WOMAN_NAMES.has(given)) return 'woman'
  if (MAN_NAMES.has(given)) return 'man'
  const last = given.at(-1) ?? ''
  if (WOMAN_ENDINGS.has(last)) return 'woman'
  if (MAN_ENDINGS.has(last)) return 'man'
  return null
}

/** 지원서 id로 만든 숫자. 같은 지원자면 늘 같다 */
function hashOf(seed: string) {
  let hash = 0
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return hash
}

/** 지원자 예시 사진 주소. 블라인드로 가린 이름이면 null이다 */
export function applicantPhoto(applicationId: string, name: string): string | null {
  if (!/^[가-힣]{2,4}$/.test(name.trim())) return null
  const hash = hashOf(applicationId)
  // 이름으로 성별을 짐작하지 못하면 지원자마다 남자 · 여자를 번갈아 고른다 (같은 지원자는 늘 같다)
  const gender = guessGender(name) ?? (hash % 2 === 0 ? 'man' : 'woman')
  // 번갈아 고를 때 쓴 끝자리와 겹치지 않게 다음 자리로 사진 번호를 고른다
  return `${PHOTO_BASE}/${gender}_${(Math.floor(hash / 2) % PHOTOS_PER_GENDER) + 1}.jpg`
}
