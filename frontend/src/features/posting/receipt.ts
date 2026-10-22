import type { Schemas } from '@/lib/api/client'

export type Receipt = Pick<Schemas['ReceiptView'], 'subject' | 'body'>

/** 접수 확인 메일에 쓸 수 있는 변수. 보낼 때 backend가 실제 값으로 바꾼다 */
export const RECEIPT_VARIABLES = ['{지원자명}', '{회사명}', '{공고명}', '{지원번호}']

/** 게시 전 미리보기용으로 변수를 채운다. 지원자 값은 예시다 */
export function previewReceipt(text: string, companyName: string, title: string) {
  return text
    .replaceAll('{회사명}', companyName)
    .replaceAll('{공고명}', title || '공고명')
    .replaceAll('{지원자명}', '홍길동')
    .replaceAll('{지원번호}', '1')
}
