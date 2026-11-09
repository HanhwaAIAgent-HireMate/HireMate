import { ImagePlus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'

/** 증명사진으로 받는 파일 */
const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_PHOTO_BYTES = 5 * 1024 * 1024

/** 지원서의 선택 증명사진을 미리 보여 준다. */
export function PhotoField({ onChange }: { onChange: (file: File | null) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [photo, setPhoto] = useState<{ url: string; name: string } | null>(null)

  // 미리보기 주소는 사진을 바꾸거나 화면을 떠날 때 풀어 준다
  useEffect(() => () => void (photo && URL.revokeObjectURL(photo.url)), [photo])

  const choose = (file: File | undefined) => {
    if (!file) return
    if (!PHOTO_TYPES.includes(file.type)) {
      toast.error('JPG, PNG, WEBP 사진만 올릴 수 있어요.')
      return
    }
    if (file.size > MAX_PHOTO_BYTES) {
      toast.error('사진은 5MB까지 올릴 수 있어요.')
      return
    }
    setPhoto({ url: URL.createObjectURL(file), name: file.name })
    onChange(file)
  }

  return (
    <div className="flex items-center gap-4">
      <button
        type="button"
        aria-label={photo ? '증명사진 바꾸기' : '증명사진 올리기'}
        onClick={() => input.current?.click()}
        className="flex h-[120px] w-[90px] shrink-0 items-center justify-center overflow-hidden rounded-lg border border-dashed bg-muted/40 text-muted-foreground hover:bg-muted"
      >
        {photo ? (
          <img src={photo.url} alt="올린 증명사진" className="size-full object-cover" />
        ) : (
          <ImagePlus className="size-6" />
        )}
      </button>
      <div className="space-y-1.5 text-xs text-muted-foreground">
        <p>{photo ? photo.name : '3:4 비율의 증명사진을 올려 주세요.'}</p>
        <p>JPG, PNG, WEBP, 5MB까지</p>
        <div className="flex gap-2">
          <Button type="button" size="sm" variant="outline" onClick={() => input.current?.click()}>
            {photo ? '바꾸기' : '사진 올리기'}
          </Button>
          {photo && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                setPhoto(null)
                onChange(null)
              }}
            >
              <X />
              빼기
            </Button>
          )}
        </div>
      </div>
      <input
        ref={input}
        type="file"
        accept={PHOTO_TYPES.join(',')}
        aria-label="증명사진 파일"
        className="hidden"
        onChange={(event) => {
          choose(event.target.files?.[0])
          event.target.value = ''
        }}
      />
    </div>
  )
}
