import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { clearDraft, readDraft, useInterviewDraftKey, writeDraft } from './drafts'
import { ApiError, errorMessage } from '@/lib/api/client'

/** 서버 갱신 중에도 초안을 유지하며, 충돌 시 비교 후 명시적으로 다시 저장한다. */
export function NoteEditor({
  stageId,
  applicationId,
  field,
  label,
  description,
  text,
  version,
  editable,
  save,
  reload,
}: {
  stageId: string
  applicationId: string
  field: string
  label: string
  description: string
  text: string
  version: number
  editable: boolean
  save: (text: string, version: number) => Promise<{ text: string; version: number }>
  reload: () => Promise<unknown>
}) {
  const key = useInterviewDraftKey(stageId, applicationId, field)
  const [draft] = useState(() => readDraft(key))
  const [local, setLocal] = useState({
    text: draft?.text ?? text,
    baseline: text,
    version: draft?.version ?? version,
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [conflict, setConflict] = useState(false)
  const [durable, setDurable] = useState(true)
  const dirty = local.text !== local.baseline
  const value = dirty ? local.text : text
  const changed = dirty && value !== text
  const stale = changed && (conflict || local.version !== version)
  useEffect(() => {
    clearDraft(key, text)
  }, [key, text])
  useEffect(() => {
    if (!changed) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [changed])
  async function persist(expected: number) {
    setBusy(true)
    setError('')
    try {
      const stored = await save(value, expected)
      clearDraft(key, value)
      setLocal({ text: stored.text, baseline: stored.text, version: stored.version })
      setConflict(false)
    } catch (failure) {
      setError(errorMessage(failure))
      if (failure instanceof ApiError && failure.status === 409) {
        setConflict(true)
        await reload().catch(() => {})
      }
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="space-y-2" aria-label={label}>
      <h3 className="text-sm font-semibold">{label}</h3>
      <p className="text-xs text-muted-foreground">{description}</p>
      <Textarea
        aria-label={label}
        value={value}
        rows={6}
        maxLength={10_000}
        disabled={!editable || busy}
        onChange={(event) => {
          const baseVersion = dirty ? local.version : version
          setLocal({
            text: event.target.value,
            baseline: dirty ? local.baseline : text,
            version: baseVersion,
          })
          setDurable(writeDraft(key, event.target.value, baseVersion))
        }}
      />
      {draft && changed && (
        <p role="status" className="text-xs">
          저장되지 않은 초안을 복구했어요.
        </p>
      )}
      {!durable && <p role="alert">임시저장할 수 없어요. 이동 전에 내용을 복사해 주세요.</p>}
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {stale && (
        <div className="space-y-2 rounded-lg bg-muted p-3 text-sm">
          <p>다른 화면에서 변경됐어요. 아래 최신 내용과 현재 초안을 비교해 주세요.</p>
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() =>
              void reload().catch((failure: unknown) => setError(errorMessage(failure)))
            }
          >
            최신 내용 불러오기
          </Button>
          <p className="whitespace-pre-wrap">서버 내용: {text || '(빈 메모)'}</p>
          <Button
            variant="outline"
            size="sm"
            disabled={busy}
            onClick={() => {
              clearDraft(key, value)
              setLocal({ text, baseline: text, version })
              setConflict(false)
              setError('')
            }}
          >
            초안 버리고 서버 내용 사용
          </Button>
          <Button size="sm" disabled={busy || !editable} onClick={() => void persist(version)}>
            현재 초안으로 다시 저장
          </Button>
        </div>
      )}
      {!stale && (
        <Button
          size="sm"
          variant="outline"
          disabled={!editable || !changed || busy}
          onClick={() => void persist(dirty ? local.version : version)}
        >
          {busy ? '저장 중…' : `${label} 저장`}
        </Button>
      )}
    </section>
  )
}
