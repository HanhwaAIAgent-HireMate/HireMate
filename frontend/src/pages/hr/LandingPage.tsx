import { ArrowRight } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, Navigate } from 'react-router'

import { useMe } from '@/lib/auth'
import { cn } from '@/lib/utils'

/** 첫 진입 표지. 로그인 확인을 기다리지 않고 그리며, 로그인한 계정은 콘솔로 보낸다 (면접관은 HR 콘솔이 면접관 모드로 넘긴다). */
export function LandingPage() {
  const me = useMe()
  if (me.data) return <Navigate to="/hr" replace />
  return <Cover />
}

const ROLLING_WORDS = ['공고 작성', '서류 분석', '면접 질문', '최종 리포트']

function Cover() {
  return (
    <div className="flex min-h-screen flex-col overflow-hidden bg-surface text-foreground">
      <header className="flex flex-wrap items-center justify-between gap-4 px-4 pt-7 sm:px-8 lg:px-14">
        <span className="text-[22px] font-black tracking-[-0.05em]">Hire-mate</span>
        <nav aria-label="계정" className="flex items-center gap-2">
          <Link
            to="/login"
            className="inline-flex h-11 items-center px-4 text-[15px] font-medium hover:text-neutral-600"
          >
            로그인
          </Link>
          <Link
            to="/signup"
            className="inline-flex h-11 items-center gap-2 rounded-full bg-primary px-5 text-[15px] font-bold text-primary-foreground hover:bg-primary/85"
          >
            기업 가입
            <ArrowRight className="size-4" strokeWidth={2.25} />
          </Link>
        </nav>
      </header>

      <main className="flex flex-1 flex-wrap items-center gap-12 px-4 pt-14 pb-18 sm:px-8 lg:px-14">
        <div className="flex min-w-0 flex-[1_1_560px] flex-col gap-7">
          <div className="flex flex-col gap-1 self-start">
            <span className="text-base font-bold">채용 담당자를 위한 AI 파트너</span>
            <svg aria-hidden="true" width="210" height="14" viewBox="0 0 210 14" fill="none">
              <path
                d="M2 9 C 40 2, 70 13, 105 7 S 170 2, 208 8"
                className="animate-[cover-draw_1.2s_ease-out_0.3s_both] stroke-ai [stroke-dasharray:260] motion-reduce:animate-none"
                strokeWidth="3.5"
                strokeLinecap="round"
              />
            </svg>
          </div>

          <h1 className="text-[clamp(42px,5.6vw,88px)] leading-[1.12] font-black tracking-[-0.05em]">
            <span className="sr-only">채용의 모든 단계, Hire-mate와 함께.</span>
            <span aria-hidden="true">
              채용의 모든 단계,
              <br />
              <span className="inline-block h-[1.15em] overflow-hidden rounded-[0.28em] bg-ai px-[0.22em] align-bottom text-white">
                <span className="flex animate-[cover-roll_10s_cubic-bezier(.7,0,.2,1)_infinite] flex-col items-center leading-[1.15em] motion-reduce:animate-none">
                  {[...ROLLING_WORDS, ROLLING_WORDS[0]].map((word, index) => (
                    <span key={index}>{word}</span>
                  ))}
                </span>
              </span>
              <br />
              Hire-mate와 함께.
            </span>
          </h1>

          <div className="flex flex-wrap gap-3">
            <Link
              to="/signup"
              className="inline-flex h-[54px] items-center gap-2.5 rounded-full bg-primary px-7 text-base font-bold text-primary-foreground hover:bg-primary/85"
            >
              기업 가입하고 시작하기
              <ArrowRight className="size-[18px]" strokeWidth={2.25} />
            </Link>
            <Link
              to="/login"
              className="inline-flex h-[54px] items-center rounded-full border bg-white px-7 text-base font-medium hover:bg-neutral-50"
            >
              로그인
            </Link>
          </div>
        </div>

        <SearchOrbit />
      </main>
    </div>
  )
}

type PersonKind = 'idle' | 'ai' | 'pass'

// 검토 전, AI 선택(보라 테두리), 담당자 합격(초록 배경). HR 콘솔의 표시 규칙과 같다
const ORBITS: {
  size: number
  seconds: number
  reverse: boolean
  people: { angle: number; kind: PersonKind }[]
}[] = [
  {
    size: 180,
    seconds: 40,
    reverse: false,
    people: [
      { angle: 30, kind: 'ai' },
      { angle: 160, kind: 'idle' },
      { angle: 270, kind: 'idle' },
    ],
  },
  {
    size: 300,
    seconds: 60,
    reverse: true,
    people: [
      { angle: 0, kind: 'idle' },
      { angle: 75, kind: 'ai' },
      { angle: 140, kind: 'pass' },
      { angle: 215, kind: 'idle' },
      { angle: 300, kind: 'idle' },
    ],
  },
  {
    size: 420,
    seconds: 80,
    reverse: false,
    people: [
      { angle: 20, kind: 'idle' },
      { angle: 110, kind: 'idle' },
      { angle: 190, kind: 'ai' },
      { angle: 250, kind: 'idle' },
      { angle: 330, kind: 'pass' },
    ],
  },
]

/** 오른쪽 그림: AI가 지원자 궤도를 탐색하고, 담당자가 묻는 말풍선이 떠 있다. 휴대폰에서는 숨긴다. */
function SearchOrbit() {
  return (
    <div aria-hidden="true" className="relative hidden h-[480px] min-w-0 flex-[1_1_400px] md:block">
      <div className="absolute top-1/2 left-1/2 -mt-[220px] -ml-[220px] size-[440px] rounded-full bg-violet-100" />

      {ORBITS.map((orbit) => (
        <div
          key={orbit.size}
          className="absolute top-1/2 left-1/2 animate-[cover-orbit_60s_linear_infinite] rounded-full border-[1.5px] border-dashed border-violet-300 motion-reduce:animate-none"
          style={{
            width: orbit.size,
            height: orbit.size,
            margin: -orbit.size / 2,
            animationDuration: `${orbit.seconds}s`,
            animationDirection: orbit.reverse ? 'reverse' : 'normal',
          }}
        >
          {orbit.people.map(({ angle, kind }) => {
            const radian = (angle * Math.PI) / 180
            return (
              <span
                key={angle}
                className="absolute -mt-[22px] -ml-[22px]"
                style={{
                  left: `${50 + 50 * Math.cos(radian)}%`,
                  top: `${50 + 50 * Math.sin(radian)}%`,
                }}
              >
                {/* 궤도가 돌아도 사람이 똑바로 서 있도록 반대로 돌린다 */}
                <Person
                  kind={kind}
                  style={{
                    animationDuration: `${orbit.seconds}s`,
                    animationDirection: orbit.reverse ? 'normal' : 'reverse',
                  }}
                />
              </span>
            )
          })}
        </div>
      ))}

      <div className="absolute top-1/2 left-1/2 -mt-[42px] -ml-[42px] size-[84px] animate-[cover-pulse_3s_ease-out_infinite] rounded-full bg-ai motion-reduce:hidden" />
      <div
        className="absolute top-1/2 left-1/2 -mt-[42px] -ml-[42px] size-[84px] animate-[cover-pulse_3s_ease-out_infinite] rounded-full bg-ai motion-reduce:hidden"
        style={{ animationDelay: '-1.5s' }}
      />
      <div className="absolute top-1/2 left-1/2 -mt-[42px] -ml-[42px] flex size-[84px] items-center justify-center rounded-full bg-primary shadow-[0_12px_32px_rgba(23,23,23,0.22)]">
        <svg width="38" height="38" viewBox="0 0 24 24" className="fill-violet-300">
          <path d="M12 2.5c.5 4.6 2.9 7 7.5 7.5-4.6.5-7 2.9-7.5 7.5-.5-4.6-2.9-7-7.5-7.5 4.6-.5 7-2.9 7.5-7.5z" />
          <path
            d="M19 15.5c.25 2 1.25 3 3.25 3.25-2 .25-3 1.25-3.25 3.25-.25-2-1.25-3-3.25-3.25 2-.25 3-1.25 3.25-3.25z"
            className="fill-white"
          />
        </svg>
      </div>

      <Bubble className="rounded-[18px_18px_4px_18px]" style={{ top: 18, marginLeft: -270 }}>
        Spring으로 서버를 운영해 본 지원자 찾아 줘
      </Bubble>
      <Bubble
        className="rounded-[18px_18px_18px_4px]"
        style={{ top: 196, marginLeft: 96, width: 194, animationDelay: '-1.5s' }}
      >
        <Mention name="정유민" />
        프로젝트 경험 중 우리 공고와 맞는 부분 있어?
      </Bubble>
      <Bubble
        className="rounded-[4px_18px_18px_18px]"
        style={{ top: 404, marginLeft: -236, animationDelay: '-3s' }}
      >
        NCS 직무 기준으로 면접 질문 만들어 줘
      </Bubble>
    </div>
  )
}

function Person({ kind, style }: { kind: PersonKind; style: CSSProperties }) {
  const fill = { idle: 'fill-neutral-300', ai: 'fill-violet-400', pass: 'fill-green-500' }[kind]
  return (
    <span
      className={cn(
        'flex size-11 animate-[cover-orbit_60s_linear_infinite] items-end justify-center overflow-hidden rounded-full motion-reduce:animate-none',
        kind === 'pass' ? 'bg-pass' : 'bg-white',
        kind === 'ai'
          ? 'border-[2.5px] border-ai shadow-[0_6px_16px_rgba(124,58,237,0.18)]'
          : 'shadow-[0_6px_16px_rgba(23,23,23,0.08)]',
      )}
      style={style}
    >
      <svg width={kind === 'ai' ? 28 : 30} height={kind === 'ai' ? 28 : 30} viewBox="0 0 30 30">
        <circle cx="15" cy="11" r="6" className={fill} />
        <path d="M4 30c0-6.5 5-11 11-11s11 4.5 11 11z" className={fill} />
      </svg>
    </span>
  )
}

function Bubble({
  className,
  style,
  children,
}: {
  className: string
  style: CSSProperties
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'absolute left-1/2 w-max max-w-[230px] animate-[cover-float_6s_ease-in-out_infinite] bg-white px-[15px] py-[11px] text-sm leading-[1.6] break-keep shadow-[0_10px_28px_rgba(23,23,23,0.10)] motion-reduce:animate-none',
        className,
      )}
      style={style}
    >
      {children}
    </div>
  )
}

/** AI Chat 입력창의 지원자 멘션 칩과 같은 모양. */
function Mention({ name }: { name: string }) {
  return (
    <span className="mr-1 inline-flex items-center rounded-md bg-ai-soft px-1.5 py-px text-[13px] font-bold text-ai">
      @{name}
    </span>
  )
}
