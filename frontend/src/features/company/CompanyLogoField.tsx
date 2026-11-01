import { ImageUp, Trash2 } from 'lucide-react'
import { useRef } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { COMPANY_LOGO_URL, useCompanyLogo, useMailStyle } from '@/features/company/api'
import { errorMessage } from '@/lib/api/client'

const IMAGE_TYPES = ['image/png', 'image/jpeg']
// 서버가 메일과 포스터에 맞게 줄여 저장해서 큰 그림도 받는다
const IMAGE_MAX_BYTES = 5 * 1024 * 1024

// 회사 로고 (설정 › 회사 소개). 한 번 올리면 안내 메일 머리와 새 공고 포스터에 같이 들어간다.
// 포스터 색은 로고에 맞춰 바뀌고, 메일 색은 메일 꾸밈에서 [로고에서 색 고르기]로 고른다
export function CompanyLogoField() {
  const style = useMailStyle()
  const logo = useCompanyLogo()
  const input = useRef<HTMLInputElement>(null)
  const has = style.data?.hasLogo ?? false

  const onPick = (file: File | undefined) => {
    if (input.current) input.current.value = ''
    if (!file) return
    if (!IMAGE_TYPES.includes(file.type)) {
      toast.error('PNG나 JPG 그림만 올릴 수 있어요.')
      return
    }
    if (file.size > IMAGE_MAX_BYTES) {
      toast.error('로고는 5MB까지 올릴 수 있어요.')
      return
    }
    logo.mutate(file, {
      onSuccess: () =>
        toast.success(
          '로고를 올렸어요. 포스터 색은 로고에 맞췄고, 메일 색은 메일 꾸밈에서 로고 색으로 고를 수 있어요.',
        ),
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {has && (
          <img
            src={`${COMPANY_LOGO_URL}?v=${style.dataUpdatedAt}`}
            alt="올린 회사 로고"
            className="h-10 w-auto max-w-[220px] rounded border bg-white p-1"
          />
        )}
        <Button
          variant="outline"
          size="sm"
          disabled={logo.isPending || !style.data}
          onClick={() => input.current?.click()}
        >
          <ImageUp />
          {has ? '로고 바꾸기' : '로고 올리기'}
        </Button>
        {has && (
          <Button
            variant="outline"
            size="sm"
            disabled={logo.isPending}
            onClick={() =>
              logo.mutate(null, { onError: (error) => toast.error(errorMessage(error)) })
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
        PNG · JPG, 5MB까지. 안내 메일과 공고 포스터에 들어가요.
      </p>
    </div>
  )
}
