import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import type { Schemas } from '@/lib/api/client'

export type MailPreview = Schemas['MailPreview']

/** 메일 색과 로고를 고르는 설정 (설정 › 안내 메일) */
const MAIL_SETTINGS_PATH = '/hr/settings/mail'

/** 줄여 보일 때 메일을 그리는 폭. 메일 본문 폭(600px)에 바깥 여백을 더한 크기다 */
const MAIL_WIDTH = 640

// 지원자가 받을 메일 모습. backend가 보낼 때와 같은 HTML을 만들어 주고, 화면은 스크립트를 막은 iframe에 넣는다.
// 스크립트 없이 같은 출처로만 열어, 다 그린 뒤 메일 길이에 맞게 높이를 늘린다.
// settingsLink가 있으면 그 글자로 설정 › 안내 메일로 가는 링크를 단다
// scale을 주면 메일을 실제 폭으로 그린 뒤 그 비율로 줄여 보인다. 좁은 칸에서도 PC 메일 모습 그대로 한눈에 본다
// scale이 'fit'이면 놓인 칸의 실제 폭을 재서 메일 전체가 꼭 맞게 줄인다 (스크롤 막대 · 창 크기가 바뀌면 다시 맞춘다)
export function MailFrame({
  preview,
  title,
  settingsLink,
  scale,
}: {
  preview: MailPreview | undefined
  title: string
  /** 설정으로 가는 링크 글자. 예: 메일 색 · 로고 바꾸기 */
  settingsLink?: string
  /** 줄여 보일 비율 (0~1) 또는 칸 폭에 맞추는 'fit'. 없으면 칸 폭 그대로 그린다 */
  scale?: number | 'fit'
}) {
  const [height, setHeight] = useState(480)
  /** 메일을 그린 폭. 제목이 길어 메일이 기본 폭보다 넓으면 그만큼 넓힌다 */
  const [width, setWidth] = useState(MAIL_WIDTH)
  /** 'fit'일 때 메일이 들어갈 칸의 실제 폭 */
  const [room, setRoom] = useState(0)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const element = box.current
    if (scale !== 'fit' || !element) return
    const measure = () => setRoom(element.clientWidth)
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [scale, preview])
  if (!preview) return <Skeleton className="h-[480px] w-full rounded-lg" />
  const ratio = scale === 'fit' ? (room ? Math.min(1, room / width) : 0) : (scale ?? 1)
  const frame = (
    <iframe
      title={title}
      srcDoc={preview.html}
      sandbox="allow-same-origin"
      // 높이를 메일 길이에 맞추므로 안쪽 스크롤은 쓰지 않는다. 테두리(위아래 1px)만큼 더해 끝이 잘리지 않게 한다
      scrolling="no"
      onLoad={(event) => {
        const page = event.currentTarget.contentDocument?.documentElement
        if (!page) return
        setHeight(page.scrollHeight + 2)
        // 줄여 보일 때는 메일의 실제 폭(테두리 포함)으로 그려 오른쪽이 잘리지 않게 한다
        if (scale) setWidth(Math.max(MAIL_WIDTH, page.scrollWidth + 2))
      }}
      style={
        scale
          ? { height, width, transform: `scale(${ratio})`, transformOrigin: 'top left' }
          : { height }
      }
      className={scale ? 'rounded-lg border bg-white' : 'w-full rounded-lg border bg-white'}
    />
  )
  return (
    <div className="space-y-2">
      <p className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
        <span>
          제목 <span className="font-semibold text-foreground">{preview.subject}</span>
        </span>
        {settingsLink && (
          <Link to={MAIL_SETTINGS_PATH} className="ml-auto underline">
            {settingsLink}
          </Link>
        )}
      </p>
      {scale ? (
        <div ref={box} className="w-full">
          <div className="overflow-hidden" style={{ width: width * ratio, height: height * ratio }}>
            {frame}
          </div>
        </div>
      ) : (
        frame
      )}
    </div>
  )
}
