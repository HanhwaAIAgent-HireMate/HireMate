import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

const WEEK = ['일', '월', '화', '수', '목', '금', '토']
const MINUTES = [0, 10, 20, 30, 40, 50, 59]

const pad = (value: number) => String(value).padStart(2, '0')

/** 'YYYY-MM-DDTHH:mm' (datetime-local과 같은 로컬 시간 글) → 날짜 · 시 · 분 */
function parse(value: string) {
  const [date = '', time = '00:00'] = value.split('T')
  const [hour = 0, minute = 0] = time.split(':').map(Number)
  return { date, hour, minute }
}

function join(date: string, hour: number, minute: number) {
  return `${date}T${pad(hour)}:${pad(minute)}`
}

function dayText(year: number, month: number, day: number) {
  return `${year}-${pad(month + 1)}-${pad(day)}`
}

/** 화면에 보일 글. 예: 2026. 11. 05. 14:00 */
function shownText(value: string) {
  const { date, hour, minute } = parse(value)
  return `${date.replaceAll('-', '. ')}. ${pad(hour)}:${pad(minute)}`
}

/**
 * 달력에서 날짜를, 목록에서 시 · 분을 골라 [확인]으로 정하는 칸. 글자로 직접 쓸 수 없어 없는 날짜(2월 31일 등)가 들어가지 않는다.
 * 값은 datetime-local과 같은 'YYYY-MM-DDTHH:mm' 로컬 시간 글이다. min보다 앞선 날짜는 고를 수 없다.
 */
export function DateTimePicker({
  value,
  onChange,
  min,
  label,
  className,
}: {
  value: string
  onChange: (value: string) => void
  /** 고를 수 있는 가장 이른 때 ('YYYY-MM-DDTHH:mm') */
  min?: string
  /** 칸 이름. 버튼의 aria-label이 된다 */
  label: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(value)
  const [month, setMonth] = useState(() => monthOf(value || min))

  const start = (next: boolean) => {
    if (next) {
      // 열 때마다 지금 값(없으면 고를 수 있는 가장 이른 때)에서 시작한다
      const initial = value || min || ''
      setDraft(initial)
      setMonth(monthOf(initial))
    }
    setOpen(next)
  }

  const picked = parse(draft)
  const minDate = min ? parse(min).date : ''
  const tooEarly = Boolean(min && draft && draft < min)
  const first = new Date(month.year, month.month, 1).getDay()
  const days = new Date(month.year, month.month + 1, 0).getDate()
  const minutes = [...new Set([...MINUTES, picked.minute])].sort((a, b) => a - b)

  const move = (step: number) =>
    setMonth(({ year, month: current }) => {
      const next = new Date(year, current + step, 1)
      return { year: next.getFullYear(), month: next.getMonth() }
    })

  return (
    <Popover open={open} onOpenChange={start}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          aria-label={label}
          data-value={value}
          className={cn('h-9 w-full justify-between px-3 font-normal', className)}
        >
          <span className={cn(!value && 'text-muted-foreground')}>
            {value ? shownText(value) : '날짜 · 시간 고르기'}
          </span>
          <CalendarDays className="text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72">
        <div className="flex items-center justify-between">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="이전 달"
            onClick={() => move(-1)}
          >
            <ChevronLeft />
          </Button>
          <span className="font-medium">
            {month.year}년 {month.month + 1}월
          </span>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="다음 달"
            onClick={() => move(1)}
          >
            <ChevronRight />
          </Button>
        </div>
        <div className="grid grid-cols-7 gap-0.5 text-center text-xs">
          {WEEK.map((day) => (
            <span key={day} className="py-1 text-muted-foreground">
              {day}
            </span>
          ))}
          {Array.from({ length: first }, (_, index) => (
            <span key={`blank-${index}`} />
          ))}
          {Array.from({ length: days }, (_, index) => {
            const day = index + 1
            const date = dayText(month.year, month.month, day)
            const selected = date === picked.date
            return (
              <button
                key={date}
                type="button"
                aria-label={`${month.month + 1}월 ${day}일`}
                aria-pressed={selected}
                disabled={Boolean(minDate) && date < minDate}
                onClick={() => setDraft(join(date, picked.hour, picked.minute))}
                className={cn(
                  'h-8 rounded-md hover:bg-muted disabled:pointer-events-none disabled:opacity-30',
                  selected && 'bg-primary text-primary-foreground hover:bg-primary',
                )}
              >
                {day}
              </button>
            )
          })}
        </div>
        <div className="flex items-center gap-2 border-t pt-2.5">
          <span className="text-xs text-muted-foreground">시간</span>
          <select
            aria-label="시"
            value={picked.hour}
            disabled={!picked.date}
            onChange={(event) =>
              setDraft(join(picked.date, Number(event.target.value), picked.minute))
            }
            className="h-8 flex-1 rounded-md border bg-background px-2"
          >
            {Array.from({ length: 24 }, (_, hour) => (
              <option key={hour} value={hour}>
                {pad(hour)}시
              </option>
            ))}
          </select>
          <select
            aria-label="분"
            value={picked.minute}
            disabled={!picked.date}
            onChange={(event) =>
              setDraft(join(picked.date, picked.hour, Number(event.target.value)))
            }
            className="h-8 flex-1 rounded-md border bg-background px-2"
          >
            {minutes.map((minute) => (
              <option key={minute} value={minute}>
                {pad(minute)}분
              </option>
            ))}
          </select>
        </div>
        {tooEarly && (
          <p role="alert" className="text-xs text-destructive">
            {min && shownText(min)}보다 앞선 시간은 고를 수 없어요.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
            취소
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!picked.date || tooEarly}
            onClick={() => {
              onChange(draft)
              setOpen(false)
            }}
          >
            확인
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function monthOf(value: string | undefined) {
  const [year, month] = parse(value ?? '')
    .date.split('-')
    .map(Number)
  if (year && month) return { year, month: month - 1 }
  const now = new Date()
  return { year: now.getFullYear(), month: now.getMonth() }
}
