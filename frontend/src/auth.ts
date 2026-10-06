import { type QueryClient, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api, type User } from './api'

const ME_KEY = ['me']

/** Текущий пользователь: null — не вошёл, undefined — ещё загружается. */
export function useMe() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async (): Promise<User | null> => {
      try {
        return await api<User>('/auth/me')
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null
        throw error
      }
    },
    staleTime: Infinity,
  })
}

// Вход и выход в одной вкладке сообщаются остальным: cookie у вкладок общая, а кэш данных — у каждой свой.
const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('fsp-auth')

/** Сбрасывает кэш, чтобы данные одного пользователя не достались следующему, и запоминает нового. */
function setUser(queryClient: QueryClient, user: User | null) {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] })
  queryClient.setQueryData(ME_KEY, user)
}

/** Сессия закончилась на этой вкладке: выход, удаление учётной записи либо ответ 401 от сервера. */
export function signedOut(queryClient: QueryClient) {
  setUser(queryClient, null)
  channel?.postMessage('changed')
}

/** Подключает обработку смены пользователя в другой вкладке; вызывается один раз при старте. */
export function watchAuth(queryClient: QueryClient) {
  channel?.addEventListener('message', () => {
    // Кто вошёл теперь, знает только сервер: чужие данные убираются, пользователь запрашивается заново.
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_KEY[0] })
    queryClient.invalidateQueries({ queryKey: ME_KEY })
  })
}

/** Запрос отклонён, потому что сессии больше нет (истекла либо завершена в другой вкладке). */
export function isSessionLost(queryClient: QueryClient, error: unknown) {
  return error instanceof ApiError && error.status === 401 && Boolean(queryClient.getQueryData(ME_KEY))
}

export function useAuthActions() {
  const queryClient = useQueryClient()
  return {
    async login(email: string, password: string) {
      const user = await api<User>('/auth/login', { method: 'POST', body: { email, password } })
      setUser(queryClient, user)
      channel?.postMessage('changed')
      return user
    },
    /** Вход завершён на сервере другим способом (через ФСП ID): остаётся запомнить пользователя. */
    signedIn(user: User) {
      setUser(queryClient, user)
      channel?.postMessage('changed')
    },
    async logout() {
      await api('/auth/logout', { method: 'POST' })
      signedOut(queryClient)
    },
  }
}

export const homePath = (user: User) => (user.role === 'candidate' ? '/candidate/assessment' : '/employer/needs')
