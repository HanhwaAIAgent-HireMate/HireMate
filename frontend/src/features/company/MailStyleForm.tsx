import { ImageUp, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  useDeleteMailImage,
  useMailStyle,
  useMailStylePreview,
  useReceiptTemplatePreview,
  useSaveMailLook,
  useUploadMailImage,
  type MailImage,
  type MailLook,
  type MailStyle,
} from '@/features/company/api'
import { GUIDE_BOXES, HEADERS, isTooLight, normalizeColor } from '@/features/company/mailColor'
import { SettingsRow, SettingsSection } from '@/features/company/SettingsSection'
import { MailFrame } from '@/features/notice/MailFrame'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const IMAGE_TYPES = ['image/png', 'image/jpeg']
// 서버가 메일에 맞는 크기로 줄여 저장해서 큰 그림도 받는다
const IMAGE_MAX_BYTES = 5 * 1024 * 1024
/** 회사 로고를 올리는 곳 */
const COMPANY_SETTINGS_PATH = '/hr/settings'
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
  const [header, setHeader] = useState(saved.header)
  const [box, setBox] = useState(saved.box)
  const look: MailLook = { color: main.color, header, box }
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
    if (main.invalid) {
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
      {/* 넓은 화면에서는 미리보기를 오른쪽에 붙여 두어, 왼쪽 칸을 고치는 동안에도 바로 보이게 한다.
          설정과 미리보기를 1 : 2로 나눠 메일을 실제 폭으로 크게 본다 */}
      <div className="grid gap-x-8 gap-y-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="min-w-0 space-y-5">
          {/* 로고는 설정 › 회사 소개에서 올려 포스터와 같이 쓴다. 로고를 올리면 서버가 메일 대표 색도 로고 색으로 바꾼다 */}
          <SettingsRow label="로고">
            <div className="space-y-2">
              {saved.hasLogo && (
                <img
                  src={`${IMAGES.logo.url}?v=${version}`}
                  alt="회사 로고"
                  className="h-10 w-auto max-w-[220px] rounded border bg-white p-1"
                />
              )}
              <p className="text-xs text-muted-foreground">
                {saved.hasLogo
                  ? '로고는 '
                  : '로고가 없어 메일 머리에 회사 이름을 글자로 써요. 로고는 '}
                <Link to={COMPANY_SETTINGS_PATH} className="underline">
                  설정 › 회사 소개
                </Link>
                에서 올리고 바꿔요.
                {saved.hasLogo &&
                  ' 올리면 대표 색도 로고 색으로 바뀌고, 아래에서 다시 고를 수 있어요.'}
              </p>
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
          <SettingsRow label="머리 모양">
            <div className="space-y-1.5">
              <Dropdown name="머리 모양" options={HEADERS} value={header} onChange={setHeader} />
              {header === 'BANNER' && !saved.hasBanner && (
                <p className="text-xs text-amber-700">
                  아직 배너가 없어요. 배너를 올리기 전에는 색 띠로 보내요.
                </p>
              )}
            </div>
          </SettingsRow>
          <SettingsRow label="안내 상자">
            <Dropdown name="안내 상자 모양" options={GUIDE_BOXES} value={box} onChange={setBox} />
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
          />
        </div>
      </div>
    </SettingsSection>
  )
}

function ColorField({
  name,
  input,
  lightWarning,
}: {
  name: string
  input: ReturnType<typeof useColorInput>
  lightWarning: string
}) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-2 text-sm">
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

/** 머리 · 안내 상자 모양 고르기. 설정 칸을 좁게 쓰려고 드롭다운으로 두고, 고른 모양의 설명을 아래에 보인다 */
function Dropdown<T extends string>({
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
  const selected = options.find((option) => option.value === value)
  return (
    <div className="space-y-1">
      <Select value={value} onValueChange={(next) => onChange(next as T)}>
        <SelectTrigger aria-label={name} className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selected && <p className="text-xs text-muted-foreground">{selected.hint}</p>}
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
