import { FileText, Plus, X } from 'lucide-react'
import { useRef } from 'react'
import { toast } from 'sonner'

import {
  companyFileUrl,
  useCompanyFiles,
  useDeleteCompanyFile,
  useUploadCompanyFile,
  type FileCategory,
} from '@/features/company/api'
import { errorMessage } from '@/lib/api/client'

/** 참고 자료 PDF 목록. 올리면 바로 저장된다. */
export function ReferenceFiles({ category }: { category: FileCategory }) {
  const files = useCompanyFiles(category)
  const upload = useUploadCompanyFile(category)
  const remove = useDeleteCompanyFile(category)
  const input = useRef<HTMLInputElement>(null)

  const onPick = (picked: FileList | null) => {
    for (const file of Array.from(picked ?? [])) {
      upload.mutate(file, { onError: (error) => toast.error(errorMessage(error)) })
    }
    if (input.current) input.current.value = ''
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {files.data?.map((file) => (
        <span
          key={file.fileId}
          className="group inline-flex h-8 items-center gap-1.5 rounded-md border bg-background px-2.5 text-sm font-medium"
        >
          <FileText className="size-3.5 text-muted-foreground" />
          <a
            href={companyFileUrl(file.fileId)}
            target="_blank"
            rel="noreferrer"
            className="hover:underline"
          >
            {file.name}
          </a>
          <button
            type="button"
            aria-label={`${file.name} 삭제`}
            className="hidden text-muted-foreground group-hover:inline hover:text-foreground"
            onClick={() => remove.mutate(file.fileId)}
          >
            <X className="size-3.5" />
          </button>
        </span>
      ))}
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={upload.isPending}
        className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-sm font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        <Plus className="size-3.5" />
        PDF
      </button>
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        hidden
        onChange={(event) => onPick(event.target.files)}
      />
    </div>
  )
}
