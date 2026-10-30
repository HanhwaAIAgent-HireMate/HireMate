import { ChevronDown, Info } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

type Section = { label: string; value: string }

const BADGE_COLORS: Record<string, string> = {
  '직무 개념과 적용 판단': 'border-sky-200 bg-sky-50 text-sky-800',
  '가상 업무 상황 판단': 'border-violet-200 bg-violet-50 text-violet-800',
  '필수 조건 근거 없음': 'border-amber-200 bg-amber-50 text-amber-800',
  '우대 조건 근거 없음': 'border-amber-200 bg-amber-50 text-amber-800',
  '필수 조건 일부 확인': 'border-amber-200 bg-amber-50 text-amber-800',
  '우대 조건 일부 확인': 'border-amber-200 bg-amber-50 text-amber-800',
  // 🎤 위험 신호(개인정보 · 안전 · 승인 절차)는 면접관이 놓치지 않게 다른 색으로 구분한다
  '위험 신호 확인': 'border-rose-200 bg-rose-50 text-rose-800',
  '주장 근거 확인': 'border-orange-200 bg-orange-50 text-orange-800',
  '구체 업무 확인': 'border-teal-200 bg-teal-50 text-teal-800',
  '확인 필요': 'border-amber-200 bg-amber-50 text-amber-800',
  '주장만 있음': 'border-amber-200 bg-amber-50 text-amber-800',
  '본인 역할 확인': 'border-teal-200 bg-teal-50 text-teal-800',
  '사실 관계 확인': 'border-slate-200 bg-slate-50 text-slate-700',
  '이전 면접에서 확인 안 됨': 'border-indigo-200 bg-indigo-50 text-indigo-800',
  '메모 참고 확인': 'border-violet-200 bg-violet-50 text-violet-800',
  // 🎤 1분 자기소개처럼 모든 지원자에게 똑같이 묻는 질문 (10/30: '공통' 표시를 다시 붙임)
  공통: 'border-slate-200 bg-slate-50 text-slate-700',
  // 🎤 면접 중 답변을 듣고 이어 물은 질문 (AI 제안을 골랐거나 면접관이 직접 씀)
  꼬리질문: 'border-fuchsia-200 bg-fuchsia-50 text-fuchsia-800',
}

const FIELD =
  /^(이 질문의 자리|이전 면접 질문|이전 면접 답변|질문 유형|확인할 내용|생성 방식|질문 기준(?: · 회사 인재상| · 조직 문화)?|출처|원문|기준 문구|공통 질문|앞 질문):\s*(.*)$/

// 🎤 지원자가 직접 쓴 문서. 이 출처의 원문은 “ ”로 감싸 '지원자 문장을 그대로 가져왔다'는 것을 보여 준다
const APPLICANT_DOCUMENTS = ['이력서', '자기소개서', '자소서']

// 출처 표시를 짧게 줄인다: 자기소개서 → 자소서, '공고의 직무·평가 기준' → 공고
function sourceLabel(value: string): string {
  if (value === '자기소개서') return '자소서'
  if (value.startsWith('공고')) return '공고'
  return value
}

// 저장된 표시 문구만 항목으로 나눈다. 없는 근거나 출처를 새로 만들지 않는다.
function sections(reason: string): Section[] {
  const result: Section[] = []
  for (const line of reason.split(/\r\n?|\n/)) {
    const match = FIELD.exec(line)
    if (match) result.push({ label: match[1], value: match[2] })
    else if (result.length) result[result.length - 1].value += `\n${line}`
    else result.push({ label: '참고 내용', value: line })
  }
  return result
}

export function QuestionReason({
  text,
  reason,
  source,
  leading,
}: {
  text: string
  reason?: string | null
  source: 'AI' | 'MANUAL'
  /** 🎤 첫 줄 맨 앞(유형 배지 왼쪽)에 둘 요소 (예: 담당 인사 · 실무 선택 상자). 오른쪽 끝의 삭제(X) 버튼과 떨어지게 왼쪽에 둔다 */
  leading?: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const rows = reason ? sections(reason) : []
  const criterion = rows.find((row) => row.label === '질문 기준')
  const purpose = rows.find((row) => row.label === '확인할 내용')
  const type = rows.find((row) => row.label === '질문 유형')
  const method = rows.find((row) => row.label === '생성 방식')
  const slot = rows.find((row) => row.label === '이 질문의 자리')
  const material = rows.filter(
    (row) =>
      !['질문 기준', '확인할 내용', '질문 유형', '생성 방식', '이 질문의 자리'].includes(row.label),
  )
  const common = source === 'AI' && /^(?:Q\d+\. )?1분 자기소개 부탁드립니다\.$/.test(text)
  const hasMaterial = material.length > 0
  const samePurpose = !!criterion && !!purpose && criterion.value.trim() === purpose.value.trim()

  return (
    <div className="min-w-0 flex-1 text-sm">
      {/* 🎤 첫 줄: [담당(leading)] [질문 유형 배지(자기소개는 '공통')] 순서로 왼쪽부터 둔다 (10/30).
          배지는 질문 바로 위에 두어, 면접관이 어떤 질문인지 먼저 보고 읽게 한다 */}
      {(common || type || leading) && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          {leading && <div className="shrink-0">{leading}</div>}
          {common ? (
            <ReasonBadge label="질문 유형" value="공통" />
          ) : (
            type && <ReasonBadge label="질문 유형" value={type.value} />
          )}
        </div>
      )}
      <p className="leading-relaxed font-semibold">{text}</p>
      <div className="mt-1 flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-label="질문 생성 근거"
          aria-expanded={open}
          aria-controls={id}
          onClick={() => setOpen((value) => !value)}
          className={`inline-flex min-h-7 items-center gap-1 rounded px-0.5 text-xs font-medium hover:text-ai focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${open ? 'text-ai' : 'text-muted-foreground'}`}
        >
          <Info className="size-3.5" aria-hidden="true" />
          근거
          <ChevronDown
            className={`size-3 transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''}`}
            aria-hidden="true"
          />
        </button>
      </div>
      <div id={id} hidden={!open} role="region" aria-label="질문 생성 근거">
        <div className="mt-1 space-y-4 rounded-xl border border-border/70 bg-muted/30 p-4 text-sm leading-relaxed text-foreground">
          {common ? (
            <>
              <ReasonSection label="근거">
                이 전형의 모든 지원자에게 똑같이 묻는 자기소개 질문입니다.
              </ReasonSection>
              <ReasonSection label="면접 확인 부분">
                지원자의 주요 경험과 지원 동기를 먼저 듣기 위한 질문입니다.
              </ReasonSection>
            </>
          ) : reason ? (
            <>
              {slot && (
                <div className="flex flex-wrap items-center gap-2">
                  <ReasonBadge label="이 질문의 자리" value={slot.value} />
                </div>
              )}
              <ReasonSection label="근거">
                {!hasMaterial &&
                  (criterion ? (
                    <SourceRow label="공고" text={criterion.value} />
                  ) : (
                    <p>이 질문에 연결된 원문이나 기준이 별도로 기록되지 않았습니다.</p>
                  ))}
                {material.map((row, index) => {
                  if (
                    row.label === '출처' &&
                    ['원문', '기준 문구'].includes(material[index + 1]?.label)
                  )
                    return null
                  const previous = material[index - 1]
                  if (row.label === '원문' || row.label === '기준 문구') {
                    const label = previous?.label === '출처' ? sourceLabel(previous.value) : ''
                    return (
                      <SourceRow
                        key={index}
                        label={label}
                        text={row.value}
                        verbatim
                        quoted={row.label === '원문' && APPLICANT_DOCUMENTS.includes(label)}
                      />
                    )
                  }
                  return (
                    <ReasonSection
                      key={index}
                      label={row.label === '출처' ? '참고한 자료' : row.label}
                    >
                      {row.value}
                    </ReasonSection>
                  )
                })}
                {/* 서류 문장을 인용한 질문이면 어떤 공고 기준과 이어지는지도 보여 준다 */}
                {hasMaterial && criterion && <SourceRow label="공고" text={criterion.value} />}
              </ReasonSection>
              <ReasonSection label="면접 확인 부분">
                {purpose && !(samePurpose && !hasMaterial)
                  ? purpose.value
                  : '구체적인 확인 목적은 별도로 기록되지 않았습니다.'}
              </ReasonSection>
              {method && <ReasonSection label="생성 방식">{method.value}</ReasonSection>}
            </>
          ) : (
            <ReasonSection
              label={source === 'MANUAL' ? '면접관이 직접 추가한 질문' : '기록된 근거가 없어요'}
            >
              {source === 'MANUAL'
                ? '담당자가 직접 추가한 질문입니다. AI 생성 근거는 없습니다.'
                : '이 질문은 생성 근거가 저장되기 전에 만들어졌습니다. 새로 생성하는 질문부터 근거를 확인할 수 있습니다.'}
            </ReasonSection>
          )}
        </div>
      </div>
    </div>
  )
}

function ReasonSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold text-ai">{label}</p>
      <div className="space-y-2 break-words whitespace-pre-wrap">{children}</div>
    </div>
  )
}

// 근거 한 줄: [출처] 문장. 출처 표시가 '근거' 제목과 같은 왼쪽 줄에서 시작하고,
//   문장은 표시 바로 뒤에 이어 쓴다 (줄이 넘어가면 같은 왼쪽 줄부터 이어진다)
//   verbatim: 문서 · 메모에서 그대로 옮긴 원문이면 blockquote, 저장된 기준 이름이면 일반 문단
//   quoted: 지원자가 쓴 문장이면 “ ”로 감싼다
function SourceRow({
  label,
  text,
  verbatim = false,
  quoted = false,
}: {
  label: string
  text: string
  verbatim?: boolean
  quoted?: boolean
}) {
  const Body = verbatim ? 'blockquote' : 'p'
  return (
    <Body className="min-w-0 leading-6 break-words whitespace-pre-wrap">
      {label && (
        <span className="mr-1.5 inline-flex rounded-full border bg-background px-2 align-middle text-xs leading-5 font-medium text-muted-foreground">
          {label}
        </span>
      )}
      <span className="align-middle">{quoted ? `“${text}”` : text}</span>
    </Body>
  )
}

function ReasonBadge({ label, value }: { label: string; value: string }) {
  return (
    <span
      aria-label={`${label}: ${value}`}
      className={`inline-flex max-w-full items-center rounded-full border px-3 py-1 text-xs leading-5 font-medium ${BADGE_COLORS[value] || 'border-border bg-background text-muted-foreground'}`}
    >
      {value}
    </span>
  )
}
