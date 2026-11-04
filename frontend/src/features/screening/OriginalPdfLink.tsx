import { ExternalLink } from 'lucide-react'
import { useState } from 'react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

/**
 * 원본 PDF 열기. 블라인드 채용에서 원본에 가린 정보(출신 학교 · 학점)가 그대로 있으면 열기 전에 알린다.
 * 원본을 확인해야 할 때가 있어 막지는 않는다. 가린 정보가 없으면 바로 연다
 */
export function OriginalPdfLink({ href, hidden }: { href: string; hidden: string[] }) {
  const [confirming, setConfirming] = useState(false)
  const className = 'inline-flex items-center gap-1 hover:text-foreground'
  if (hidden.length === 0) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={className}>
        <ExternalLink className="size-3" />
        원본 PDF
      </a>
    )
  }
  return (
    <>
      <button type="button" onClick={() => setConfirming(true)} className={className}>
        <ExternalLink className="size-3" />
        원본 PDF
      </button>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>원본 PDF를 열까요?</AlertDialogTitle>
            <AlertDialogDescription>
              이 원본에는 블라인드로 가린 {subject(hidden.join(' · '))} 그대로 있어요. 열면 화면에서
              가린 정보를 보게 돼요.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                window.open(href, '_blank', 'noreferrer')
                setConfirming(false)
              }}
            >
              열기
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

/** 받침이 있으면 '이', 없으면 '가'를 붙인다 (출신 학교가, 학점이) */
function subject(word: string) {
  const last = word.charCodeAt(word.length - 1) - 0xac00
  const batchim = last >= 0 && last <= 11171 && last % 28 !== 0
  return word + (batchim ? '이' : '가')
}
