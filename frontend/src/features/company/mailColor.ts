/** 메일 색 추천. 흰 바탕에서 글자가 잘 보이는 진한 색이다 */
export const MAIL_COLORS = [
  { label: '남색', value: '#1e3a5f' },
  { label: '파랑', value: '#1d4ed8' },
  { label: '초록', value: '#047857' },
  { label: '보라', value: '#6d28d9' },
  { label: '자주', value: '#9d174d' },
  { label: '회색', value: '#374151' },
]

/** 보조 색 추천. 대표 색 추천과 잘 구분되면서 흰 바탕에서 글자가 보이는 색이다 */
export const ACCENT_COLORS = [
  { label: '주황', value: '#c2410c' },
  { label: '호박', value: '#b45309' },
  { label: '청록', value: '#0f766e' },
  { label: '하늘', value: '#0369a1' },
  { label: '장미', value: '#be123c' },
]

/** 메일 머리 모양. 값은 서버의 MailBrand.Header다 */
export const HEADERS = [
  { value: 'LINE', label: '얇은 색 줄', hint: '맨 위 색 줄과 왼쪽 로고' },
  { value: 'BAND', label: '색 띠', hint: '대표 색 띠 안에 로고와 제목' },
  { value: 'CENTER', label: '가운데 로고', hint: '옅은 색 바탕에 로고와 회사 이름' },
  { value: 'BANNER', label: '배너 그림', hint: '맨 위에 올린 배너' },
] as const

/** 안내 상자 모양. 값은 서버의 MailBrand.GuideBox다 */
export const GUIDE_BOXES = [
  { value: 'FILL', label: '옅은 바탕', hint: '회색 바탕 상자' },
  { value: 'OUTLINE', label: '테두리', hint: '보조 색 테두리 상자' },
  { value: 'ROWS', label: '줄 표', hint: '상자 없이 줄로 나눈 표' },
] as const

/** 색 코드를 #rrggbb로 맞춘다. 앞의 #는 빼도 되고 대소문자는 상관없다. 6자리가 아니면 null */
export function normalizeColor(input: string) {
  const match = /^#?([0-9a-f]{6})$/i.exec(input.trim())
  return match ? `#${match[1].toLowerCase()}` : null
}

/**
 * 흰 바탕에서 글자가 잘 안 보일 만큼 밝은 색인지. 흰색과의 명암비가 3:1보다 낮으면 밝다고 본다
 * (WCAG의 큰 글자 기준. 메일의 회사 이름과 안내 상자 제목이 이 색 글자다)
 */
export function isTooLight(color: string) {
  const channels = [1, 3, 5].map((start) => {
    const value = parseInt(color.slice(start, start + 2), 16) / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  const luminance = 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
  return 1.05 / (luminance + 0.05) < 3
}
