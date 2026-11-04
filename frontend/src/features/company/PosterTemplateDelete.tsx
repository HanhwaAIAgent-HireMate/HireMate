import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { useDeletePosterTemplate } from '@/features/posting/poster-api'
import type { PosterBrand } from '@/features/posting/poster-design'
import { errorMessage } from '@/lib/api/client'

export function PosterTemplateDelete({
  id,
  name,
  disabled = false,
  onDeleted,
}: {
  id: string
  name: string
  disabled?: boolean
  onDeleted?: (brand: PosterBrand) => void
}) {
  const [open, setOpen] = useState(false)
  const remove = useDeletePosterTemplate()
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          aria-label={`${name} 템플릿 삭제`}
          disabled={disabled || remove.isPending}
          className="absolute top-1.5 right-1.5 z-10 size-6 rounded-full bg-background shadow-sm [&_svg]:size-3.5"
        >
          <Trash2 />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>템플릿을 삭제할까요?</DialogTitle>
          <DialogDescription>
            ‘{name}’을 템플릿 목록에서 삭제해요. 현재 선택한 템플릿이면 설정에 저장한 기본
            템플릿으로 돌아가요. 이미 저장한 공고는 유지돼요. 삭제한 템플릿은 복구할 수 없어요.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" disabled={remove.isPending} onClick={() => setOpen(false)}>
            취소
          </Button>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(id, {
                onSuccess: (brand) => {
                  onDeleted?.(brand)
                  setOpen(false)
                  toast.success('템플릿을 삭제했어요.')
                },
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
          >
            {remove.isPending ? '삭제 중…' : '삭제'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
