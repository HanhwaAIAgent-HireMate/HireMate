import { ImageUp, Pipette, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  useDeleteMailImage,
  useMailStyle,
  useMailStylePreview,
  useReceiptTemplatePreview,
  useSaveMailLook,
  useSuggestMailColors,
  useUploadMailImage,
  type MailColorSuggestion,
  type MailImage,
  type MailLook,
  type MailStyle,
} from '@/features/company/api'
import {
  ACCENT_COLORS,
  GUIDE_BOXES,
  HEADERS,
  isTooLight,
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
  const logoColors = useLogoColors((suggestion) => {
    if (!suggestion.color) return
    main.pick(suggestion.color)
    setUseAccent(suggestion.accent !== null)
    if (suggestion.accent) accent.pick(suggestion.accent)
  })
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
  // 미리보기는 하나만 두고 예시 안내 메일과 접수 확인 메일을 바꿔 본다. 둘 다 고르는 중인 꾸밈으로 그린다
  const [sample, setSample] = useState<'notice' | 'receipt'>('notice')
  const notice = useMailStylePreview(previewLook)
  const receipt = useReceiptTemplatePreview(previewLook)
  const preview = sample === 'notice' ? notice : receipt

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
    <SettingsSection title="메일 꾸밈" saving={save.isPending} onSave={onSave} wide>
      <p className="text-sm text-muted-foreground">
        모든 안내 메일과 접수 확인 메일에 같은 색과 모양이 들어가요.
      </p>
      {/* 넓은 화면에서는 미리보기를 오른쪽에 붙여 두어, 아래 칸을 고치는 동안에도 바로 보이게 한다 */}
      <div className="grid gap-x-8 gap-y-5 xl:grid-cols-[minmax(0,1fr)_460px]">
        <div className="min-w-0 space-y-5">
          {/* 그림을 먼저 올리면 로고에서 고른 색이 아래 색 칸에 채워진다 */}
          <SettingsRow label="로고">
            <div className="space-y-2">
              <ImageField
                kind="logo"
                has={saved.hasLogo}
                version={version}
                onUploaded={logoColors.run}
                hint="PNG · JPG, 5MB까지. 메일 머리에 맞게 줄여서 저장하고, 로고에서 메일 색을 골라 채워요. 올리지 않으면 회사 이름을 글자로 써요."
              />
              <LogoColors
                colors={logoColors}
                hasLogo={saved.hasLogo}
                onPick={(color) => main.pick(color)}
              />
            </div>
          </SettingsRow>
          <SettingsRow label="배너">
            <ImageField
              kind="banner"
              has={saved.hasBanner}
              version={version}
              hint="PNG · JPG, 5MB까지"
            />
          </SettingsRow>
          <SettingsRow label="대표 색">
            <ColorField
              name="대표 색"
              input={main}
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
        </div>
        <div className="min-w-0 space-y-1.5 xl:sticky xl:top-4 xl:max-h-[calc(100vh-2rem)] xl:self-start xl:overflow-auto">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm font-medium text-muted-foreground">미리보기</span>
            <Tabs
              value={sample}
              onValueChange={(value) => setSample(value as 'notice' | 'receipt')}
            >
              <TabsList>
                <TabsTrigger value="notice">안내 메일 예시</TabsTrigger>
                <TabsTrigger value="receipt">접수 확인 메일</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
          <p className="text-xs text-muted-foreground">
            고르는 중인 꾸밈이에요. 저장해야 메일에 들어가요.
            {sample === 'receipt' && ' 글은 위에 저장한 접수 확인 메일 양식이에요.'}
          </p>
          <MailFrame
            preview={preview.data}
            title={sample === 'notice' ? '안내 메일 예시 미리보기' : '접수 확인 메일 미리보기'}
            scale={0.7}
          />
        </div>
      </div>
    </SettingsSection>
  )
}

/**
 * 로고에서 색을 골라 대표 색과 보조 색 칸을 채운다. 로고를 올리면 바로 부르고, 올려 둔 로고로 다시 부를 수도 있다.
 * 찾은 색은 칩으로 남겨 두어 다른 색을 대표 색으로 고를 수 있다. 저장은 HR이 미리보기를 보고 한다
 */
function useLogoColors(apply: (suggestion: MailColorSuggestion) => void) {
  const suggest = useSuggestMailColors()
  const [found, setFound] = useState<MailColorSuggestion['candidates']>([])
  const run = (logo: Blob) =>
    suggest.mutate(logo, {
      onSuccess: (suggestion) => {
        setFound(suggestion.candidates)
        if (!suggestion.color) {
          toast.info('로고에서 메일 색으로 쓸 만한 색을 찾지 못했어요. 색을 직접 골라 주세요.')
          return
        }
        apply(suggestion)
        toast.success(
          suggestion.accent
            ? '로고에서 대표 색과 보조 색을 골랐어요. 미리보기를 보고 저장해 주세요.'
            : '로고에서 대표 색을 골랐어요. 미리보기를 보고 저장해 주세요.',
        )
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  return { run, found, pending: suggest.isPending }
}

function LogoColors({
  colors,
  hasLogo,
  onPick,
}: {
  colors: ReturnType<typeof useLogoColors>
  hasLogo: boolean
  onPick: (color: string) => void
}) {
  const { run, found, pending } = colors
  // 예전에 올린 로고는 저장된 그림을 받아 다시 고른다
  const again = async () => {
    const response = await fetch(IMAGES.logo.url)
    if (!response.ok) {
      toast.error('올린 로고를 불러오지 못했어요. 잠시 뒤 다시 해 주세요.')
      return
    }
    run(await response.blob())
  }

  if (!hasLogo && found.length === 0) return null
  return (
    <div className="space-y-2">
      {hasLogo && (
        <Button variant="outline" size="sm" disabled={pending} onClick={() => void again()}>
          <Pipette />
          {pending ? '색 찾는 중…' : '로고에서 색 고르기'}
        </Button>
      )}
      {found.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">로고에서 찾은 색</span>
          {found.map((candidate) => (
            <button
              key={candidate.color}
              type="button"
              title={`${candidate.color} · ${Math.round(candidate.share * 100)}%`}
              aria-label={`찾은 색 ${candidate.color}를 대표 색으로`}
              onClick={() => onPick(candidate.color)}
              className="inline-flex items-center gap-1 rounded-md border px-1.5 py-1 text-xs"
            >
              <span className="size-4 rounded-sm" style={{ background: candidate.color }} />
              {Math.round(candidate.share * 100)}%
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ColorField({
  name,
  input,
  presets = [],
  lightWarning,
}: {
  name: string
  input: ReturnType<typeof useColorInput>
  /** 눌러 고르는 추천 색 동그라미. 대표 색은 로고에서 고르거나 직접 골라 없다 */
  presets?: readonly { label: string; value: string }[]
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
        <label
          className={cn(
            'inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-2 text-sm',
            presets.length > 0 && 'ml-1',
          )}
        >
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
    <div role="radiogroup" aria-label={name} className="grid grid-cols-2 gap-2">
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
  onUploaded,
}: {
  kind: MailImage
  has: boolean
  version: number
  hint: string
  /** 올리기에 성공한 그림 파일을 받는다. 로고는 이 파일로 색을 고른다 */
  onUploaded?: (file: File) => void
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
      onSuccess: () => {
        if (onUploaded) onUploaded(file)
        else toast.success(`${image.name}를 올렸어요.`)
      },
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
