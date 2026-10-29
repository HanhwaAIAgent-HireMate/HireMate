import { ImageUp, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import {
  useDeleteMailImage,
  useMailStyle,
  useMailStylePreview,
  useSaveMailLook,
  useUploadMailImage,
  type MailImage,
  type MailLook,
  type MailStyle,
} from '@/features/company/api'
import {
  ACCENT_COLORS,
  GUIDE_BOXES,
  HEADERS,
  isTooLight,
  MAIL_COLORS,
  normalizeColor,
} from '@/features/company/mailColor'
import { SettingsRow, SettingsSection } from '@/features/company/SettingsSection'
import { MailFrame } from '@/features/notice/MailFrame'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const IMAGE_TYPES = ['image/png', 'image/jpeg']
// 서버가 메일에 맞는 크기로 줄여 저장해서 큰 그림도 받는다
const IMAGE_MAX_BYTES = 5 * 1024 * 1024
const IMAGES = {
  logo: { url: '/api/companies/me/mail-style/logo', name: '로고' },
  banner: { url: '/api/companies/me/mail-style/banner', name: '배너' },
} as const

// 모든 안내 메일과 접수 확인 메일의 색, 머리와 안내 상자 모양, 로고, 배너. 고르는 동안 예시 메일에 바로 보여 준다
export function MailStyleForm() {
  const style = useMailStyle()
  if (!style.data) return null
  return <MailStyleFields saved={style.data} version={style.dataUpdatedAt} />
}

/** 색 코드 칸과 색. code는 칸에 쓰는 중인 글자이고, 6자리가 되면 color도 바뀐다 */
function useColorInput(initial: string) {
  const [color, setColor] = useState(initial)
  const [code, setCode] = useState(initial)
  return {
    color,
    code,
    invalid: normalizeColor(code) === null,
    pick: (value: string) => {
      setColor(value)
      setCode(value)
    },
    type: (value: string) => {
      setCode(value)
      const normalized = normalizeColor(value)
      if (normalized) setColor(normalized)
    },
  }
}

function MailStyleFields({ saved, version }: { saved: MailStyle; version: number }) {
  const save = useSaveMailLook()
  const main = useColorInput(saved.color)
  // 보조 색은 끄면 저장하지 않고, 안내 상자에도 대표 색을 쓴다. 다시 켜면 고르던 색이 남아 있다
  const [useAccent, setUseAccent] = useState(saved.accent != null)
  const accent = useColorInput(saved.accent ?? ACCENT_COLORS[0].value)
  const [header, setHeader] = useState(saved.header)
  const [box, setBox] = useState(saved.box)
  const look: MailLook = {
    color: main.color,
    accent: useAccent ? accent.color : null,
    header,
    box,
  }
  // 색판을 끄는 동안 요청이 몰리지 않게 잠깐 멈췄을 때의 모양으로 미리보기를 받는다
  const [previewLook, setPreviewLook] = useState(look)
  const lookKey = JSON.stringify(look)
  useEffect(() => {
    const timer = setTimeout(() => setPreviewLook(JSON.parse(lookKey) as MailLook), 300)
    return () => clearTimeout(timer)
  }, [lookKey])
  const preview = useMailStylePreview(previewLook)

  const onSave = () => {
    if (main.invalid || (useAccent && accent.invalid)) {
      toast.error('색 코드는 #0055A4처럼 6자리로 넣어 주세요.')
      return
    }
    save.mutate(look, {
      onSuccess: () => toast.success('메일 꾸밈을 저장했어요.'),
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  return (
    <SettingsSection title="메일 꾸밈" saving={save.isPending} onSave={onSave}>
      <p className="text-sm text-muted-foreground">
        모든 안내 메일과 접수 확인 메일에 같은 색과 모양이 들어가요.
      </p>
      <SettingsRow label="대표 색">
        <ColorField
          name="대표 색"
          input={main}
          presets={MAIL_COLORS}
          lightWarning="밝은 색이라 흰 바탕에서 회사 이름이 잘 안 보일 수 있어요."
        />
      </SettingsRow>
      <SettingsRow label="보조 색">
        <div className="space-y-2">
          <label className="flex items-center gap-2 pt-1.5 text-sm">
            <Checkbox
              checked={useAccent}
              onCheckedChange={(checked) => setUseAccent(checked === true)}
            />
            안내 상자에 다른 색 쓰기
          </label>
          {useAccent ? (
            <ColorField
              name="보조 색"
              input={accent}
              presets={ACCENT_COLORS}
              lightWarning="밝은 색이라 흰 바탕에서 안내 상자 제목이 잘 안 보일 수 있어요."
            />
          ) : (
            <p className="text-xs text-muted-foreground">
              끄면 안내 상자 제목과 테두리도 대표 색이에요.
            </p>
          )}
        </div>
      </SettingsRow>
      <SettingsRow label="머리 모양">
        <div className="space-y-1.5">
          <Choices name="머리 모양" options={HEADERS} value={header} onChange={setHeader} />
          {header === 'BANNER' && !saved.hasBanner && (
            <p className="text-xs text-amber-700">
              아직 배너가 없어요. 배너를 올리기 전에는 색 띠로 보내요.
            </p>
          )}
        </div>
      </SettingsRow>
      <SettingsRow label="안내 상자">
        <Choices name="안내 상자 모양" options={GUIDE_BOXES} value={box} onChange={setBox} />
      </SettingsRow>
      <SettingsRow label="로고">
        <ImageField
          kind="logo"
          has={saved.hasLogo}
          version={version}
          hint="PNG · JPG, 5MB까지. 메일 머리에 맞게 줄여서 저장해요. 올리지 않으면 회사 이름을 글자로 써요."
        />
      </SettingsRow>
      <SettingsRow label="배너">
        <ImageField
          kind="banner"
          has={saved.hasBanner}
          version={version}
          hint="PNG · JPG, 5MB까지. 가로로 넓은 그림이 좋아요. 메일 폭에 맞게 줄여 저장하고, 머리 모양이 '배너 그림'일 때 들어가요."
        />
      </SettingsRow>
      <SettingsRow label="미리보기">
        <MailFrame preview={preview.data} title="메일 꾸밈 미리보기" />
      </SettingsRow>
    </SettingsSection>
  )
}

function ColorField({
  name,
  input,
  presets,
  lightWarning,
}: {
  name: string
  input: ReturnType<typeof useColorInput>
  presets: readonly { label: string; value: string }[]
  lightWarning: string
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {presets.map((option) => (
          <button
            key={option.value}
            type="button"
            title={option.label}
            aria-label={`${name}: ${option.label}`}
            aria-pressed={input.color === option.value}
            onClick={() => input.pick(option.value)}
            style={{ background: option.value }}
            className={cn(
              'size-7 rounded-full ring-offset-2 ring-offset-background',
              input.color === option.value && 'ring-2 ring-foreground',
            )}
          />
        ))}
        <label className="ml-1 inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-2 text-sm">
          <input
            type="color"
            aria-label={`${name} 다른 색 고르기`}
            value={input.color}
            onChange={(event) => input.pick(event.target.value)}
            className="size-5 cursor-pointer border-0 bg-transparent p-0"
          />
          다른 색
        </label>
        <Input
          aria-label={`${name} 색 코드`}
          value={input.code}
          onChange={(event) => input.type(event.target.value)}
          className="h-8 w-28 font-mono text-sm"
        />
      </div>
      {input.invalid ? (
        <p className="text-xs text-destructive">색 코드는 #0055A4처럼 6자리로 넣어 주세요.</p>
      ) : (
        isTooLight(input.color) && <p className="text-xs text-amber-700">{lightWarning}</p>
      )}
    </div>
  )
}

function Choices<T extends string>({
  name,
  options,
  value,
  onChange,
}: {
  name: string
  options: readonly { value: T; label: string; hint: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div role="radiogroup" aria-label={name} className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded-md border px-3 py-2 text-left',
            value === option.value ? 'border-foreground bg-muted' : 'hover:bg-muted/50',
          )}
        >
          <span className="block text-sm font-medium">{option.label}</span>
          <span className="block text-xs text-muted-foreground">{option.hint}</span>
        </button>
      ))}
    </div>
  )
}

function ImageField({
  kind,
  has,
  version,
  hint,
}: {
  kind: MailImage
  has: boolean
  version: number
  hint: string
}) {
  const image = IMAGES[kind]
  const upload = useUploadMailImage(kind)
  const remove = useDeleteMailImage(kind)
  const input = useRef<HTMLInputElement>(null)

  const onPick = (file: File | undefined) => {
    if (input.current) input.current.value = ''
    if (!file) return
    if (!IMAGE_TYPES.includes(file.type)) {
      toast.error('PNG나 JPG 그림만 올릴 수 있어요.')
      return
    }
    if (file.size > IMAGE_MAX_BYTES) {
      toast.error(`${image.name}는 5MB까지 올릴 수 있어요.`)
      return
    }
    upload.mutate(file, {
      onSuccess: () => toast.success(`${image.name}를 올렸어요.`),
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {has && (
          <img
            src={`${image.url}?v=${version}`}
            alt={`올린 ${image.name}`}
            className={cn(
              'w-auto rounded border bg-white p-1',
              kind === 'logo' ? 'h-10 max-w-[220px]' : 'h-14 max-w-[300px]',
            )}
          />
        )}
        <Button
          variant="outline"
          size="sm"
          disabled={upload.isPending}
          onClick={() => input.current?.click()}
        >
          <ImageUp />
          {has ? `${image.name} 바꾸기` : `${image.name} 올리기`}
        </Button>
        {has && (
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
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  )
}
