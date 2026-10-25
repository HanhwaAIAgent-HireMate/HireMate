import type { Schemas } from '@/lib/api/client'

export type Receipt = Pick<Schemas['ReceiptView'], 'subject' | 'body'>

/** 접수 확인 메일에 쓸 수 있는 변수. 보낼 때 backend가 실제 값으로 바꾼다 */
export const RECEIPT_VARIABLES = ['{지원자명}', '{회사명}', '{공고명}', '{지원번호}']
