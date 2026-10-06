import { useQuery } from '@tanstack/react-query'

import { api, type InvitationStatus, type RefItem, type Reference } from './api'

const nameOf = (items: RefItem[] | undefined, code: string | null) =>
  items?.find((item) => item.code === code)?.name ?? code ?? ''

export const toOptions = (items: RefItem[] = []) => items.map((item) => ({ value: item.code, label: item.name }))

/** Справочники и подписи к их кодам. */
export function useReference() {
  const { data } = useQuery({
    queryKey: ['reference'],
    queryFn: () => api<Reference>('/reference'),
    staleTime: Infinity,
  })
  return {
    data,
    specName: (code: string | null) => nameOf(data?.specializations, code),
    gradeName: (code: string | null) => nameOf(data?.grades, code),
    formatName: (code: string | null) => nameOf(data?.work_formats, code),
  }
}

export const INVITATION_STATUS: Record<InvitationStatus, { label: string; color: string }> = {
  sent: { label: 'Отправлено', color: 'blue' },
  viewed: { label: 'Просмотрено', color: 'yellow' },
  accepted: { label: 'Принято', color: 'green' },
  declined: { label: 'Отклонено', color: 'gray' },
}

export const FSP_LEVEL: Record<string, string> = {
  regional: 'региональный уровень',
  district: 'федеральный округ',
  federal: 'всероссийский уровень',
}

/** Все суммы на платформе — до вычета НДФЛ; пометка стоит у каждого поля и каждой вилки. */
export const SALARY_NOTE = 'до вычета НДФЛ'
/** Пояснение под полем, а не над ним: поле остаётся на одной линии с соседними в строке. */
export const NOTE_BELOW: ('label' | 'input' | 'description' | 'error')[] = ['label', 'input', 'description', 'error']

export const formatSalary = (from: number, to: number) =>
  `${from.toLocaleString('ru-RU')} – ${to.toLocaleString('ru-RU')} ₽ ${SALARY_NOTE}`

export const formatDate = (iso: string) => new Date(iso).toLocaleDateString('ru-RU')
