import { ImageUp, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  useDeleteMailLogo,
  useMailStyle,
  useMailStylePreview,
  useSaveMailColor,
  useUploadMailLogo,
  type MailStyle,
} from '@/features/company/api'
import { isTooLight, MAIL_COLORS, normalizeColor } from '@/features/company/mailColor'
import { SettingsRow, SettingsSection } from '@/features/company/SettingsSection'
import { MailFrame } from '@/features/notice/MailFrame'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const LOGO_MAX_BYTES = 500 * 1024
const LOGO_TYPES = ['image/png', 'image/jpeg']
const LOGO_URL = '/api/companies/me/mail-style/logo'

// 모든 안내 메일과 접수 확인 메일의 색과 로고. 고르는 동안 예시 메일에 바로 보여 준다
export function MailStyleForm() {
  const style = useMailStyle()
  if (!style.data) return null
  return <MailStyleFields saved={style.data} version={style.dataUpdatedAt} />
}

function MailStyleFields({ saved, version }: { saved: MailStyle; version: number }) {
  const save = useSaveMailColor()
  const upload = useUploadMailLogo()
  const remove = useDeleteMailLogo()
  const input = useRef<HTMLInputElement>(null)
  // color는 메일에 쓸 색, code는 색 코드 칸에 쓰는 중인 글자다. 코드가 6자리가 되면 color도 바뀐다
  const [color, setColor] = useState(saved.color)
  const [code, setCode] = useState(saved.color)
  // 색판을 끄는 동안 요청이 몰리지 않게 잠깐 멈췄을 때의 색으로 미리보기를 받는다
  const [previewColor, setPreviewColor] = useState(saved.color)
  useEffect(() => {
    const timer = setTimeout(() => setPreviewColor(color), 300)
    return () => clearTimeout(timer)
  }, [color])
  const preview = useMailStylePreview(previewColor)
  const codeInvalid = normalizeColor(code) === null

  const pick = (value: string) => {
    setColor(value)
    setCode(value)
  }

  const onCode = (value: string) => {
    setCode(value)
    const normalized = normalizeColor(value)
    if (normalized) setColor(normalized)
  }

  const onSave = () => {
    if (codeInvalid) {
      toast.error('색 코드는 #0055A4처럼 6자리로 넣어 주세요.')
      return
    }
    save.mutate(color, {
      onSuccess: () => toast.success('메일 색을 저장했어요.'),
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const onPick = (file: File | undefined) => {
    if (input.current) input.current.value = ''
    if (!file) return
    if (!LOGO_TYPES.includes(file.type)) {
      toast.error('PNG나 JPG 그림만 올릴 수 있어요.')
      return
    }
    if (file.size > LOGO_MAX_BYTES) {
      toast.error('로고는 500KB까지 올릴 수 있어요.')
      return
    }
    upload.mutate(file, {
      onSuccess: () => toast.success('로고를 올렸어요.'),
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  return (
    <SettingsSection title="메일 꾸밈" saving={save.isPending} onSave={onSave}>
      <p className="text-sm text-muted-foreground">
        모든 안내 메일과 접수 확인 메일에 같은 색과 로고가 들어가요.
      </p>
      <SettingsRow label="메일 색">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {MAIL_COLORS.map((option) => (
              <button
                key={option.value}
                type="button"
                title={option.label}
                aria-label={option.label}
                aria-pressed={color === option.value}
                onClick={() => pick(option.value)}
                style={{ background: option.value }}
                className={cn(
                  'size-7 rounded-full ring-offset-2 ring-offset-background',
                  color === option.value && 'ring-2 ring-foreground',
                )}
              />
            ))}
            <label className="ml-1 inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-2 text-sm">
              <input
                type="color"
                aria-label="다른 색 고르기"
                value={color}
                onChange={(event) => pick(event.target.value)}
                className="size-5 cursor-pointer border-0 bg-transparent p-0"
              />
              다른 색
            </label>
            <Input
              aria-label="색 코드"
              value={code}
              onChange={(event) => onCode(event.target.value)}
              className="h-8 w-28 font-mono text-sm"
            />
          </div>
          {codeInvalid ? (
            <p className="text-xs text-destructive">색 코드는 #0055A4처럼 6자리로 넣어 주세요.</p>
          ) : (
            isTooLight(color) && (
              <p className="text-xs text-amber-700">
                밝은 색이라 흰 바탕에서 회사 이름과 안내 제목이 잘 안 보일 수 있어요.
              </p>
            )
          )}
        </div>
      </SettingsRow>
      <SettingsRow label="로고">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            {saved.hasLogo && (
              <img
                src={`${LOGO_URL}?v=${version}`}
                alt="올린 로고"
                className="h-10 w-auto max-w-[220px] rounded border bg-white p-1"
              />
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={upload.isPending}
              onClick={() => input.current?.click()}
            >
              <ImageUp />
              {saved.hasLogo ? '로고 바꾸기' : '로고 올리기'}
            </Button>
            {saved.hasLogo && (
              <Button
                variant="outline"
                size="sm"
                disabled={remove.isPending}
                onClick={() =>
                  remove.mutate(undefined, { onError: (error) => toast.error(errorMessage(error)) })
                }
              >
                <Trash2 />
                지우기
              </Button>
            )}
            <input
              ref={input}
              type="file"
              accept="image/png,image/jpeg"
              hidden
              onChange={(event) => onPick(event.target.files?.[0])}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            PNG · JPG, 500KB까지. 메일 왼쪽 위에 들어가요. 올리지 않으면 회사 이름을 글자로 써요.
          </p>
        </div>
      </SettingsRow>
      <SettingsRow label="미리보기">
        <MailFrame preview={preview.data} title="메일 꾸밈 미리보기" />
      </SettingsRow>
    </SettingsSection>
  )
}
