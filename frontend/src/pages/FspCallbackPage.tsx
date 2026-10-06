import { Alert, Anchor, Center, Loader } from '@mantine/core'
import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { api, type User } from '../api'
import { homePath, useAuthActions } from '../auth'
import AuthCard from '../components/AuthCard'
import { notifyOk } from '../notify'

/** Возврат с ФСП ID: код обменивается на сервере, затем — в кабинет (вход) или в настройки (привязка). */
export default function FspCallbackPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { signedIn } = useAuthActions()
  const [error, setError] = useState<string | null>(null)
  // Код одноразовый: повторный вызов эффекта не должен отправить его второй раз.
  const sent = useRef(false)

  useEffect(() => {
    if (sent.current) return
    sent.current = true
    const body = { code: params.get('code') ?? '', state: params.get('state') ?? '' }
    api<{ user: User; intent: 'login' | 'link' }>('/auth/fsp/callback', { method: 'POST', body })
      .then(({ user, intent }) => {
        if (intent === 'login') {
          signedIn(user)
          navigate(homePath(user), { replace: true })
        } else {
          queryClient.invalidateQueries({ queryKey: ['candidate-profile'] })
          notifyOk('ФСП ID привязан, достижения загружены')
          navigate('/candidate/settings', { replace: true })
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Не удалось завершить вход'))
  }, [params, navigate, queryClient, signedIn])

  if (!error) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  }
  return (
    <AuthCard title="Вход через ФСП ID">
      <Alert color="red">{error}</Alert>
      <Anchor component={Link} to="/">
        Вернуться на платформу
      </Anchor>
    </AuthCard>
  )
}
