import { Alert, Anchor, Button, Divider, PasswordInput, Stack, Text, TextInput } from '@mantine/core'
import { useForm } from '@mantine/form'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'

import { ApiError, api } from '../api'
import { homePath, useAuthActions, useMe } from '../auth'
import AuthCard from '../components/AuthCard'
import ResendVerification from '../components/ResendVerification'

export default function LoginPage() {
  const { data: user } = useMe()
  const { login } = useAuthActions()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  // Адрес, с которым вход отклонён из-за неподтверждённой почты: для него предлагается повторное письмо.
  const [unverified, setUnverified] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const form = useForm({ initialValues: { email: '', password: '' } })

  if (user) return <Navigate to={homePath(user)} replace />

  // Вход через ФСП ID: сервер выдаёт адрес страницы входа провайдера, браузер переходит на неё.
  const viaFspId = async () => {
    setError(null)
    try {
      window.location.assign((await api<{ url: string }>('/auth/fsp/start')).url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось начать вход через ФСП ID')
    }
  }

  const submit = form.onSubmit(async ({ email, password }) => {
    setError(null)
    setUnverified(null)
    setLoading(true)
    try {
      navigate(homePath(await login(email, password)))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось войти')
      if (e instanceof ApiError && e.status === 403) setUnverified(email)
    } finally {
      setLoading(false)
    }
  })

  return (
    <AuthCard title="Вход">
      <form onSubmit={submit}>
        <Stack>
          {error && <Alert color="red">{error}</Alert>}
          {unverified && <ResendVerification email={unverified} />}
          <TextInput label="Электронная почта" type="email" required {...form.getInputProps('email')} />
          <PasswordInput label="Пароль" required {...form.getInputProps('password')} />
          <Button type="submit" loading={loading}>
            Войти
          </Button>
          <Divider label="или" />
          <Button variant="default" onClick={viaFspId}>
            Войти через ФСП ID
          </Button>
          <Text size="xs" c="dimmed">
            Для участников соревнований ФСП: профиль кандидата создаётся при первом входе, достижения
            подтягиваются из реестра. Продолжая, вы соглашаетесь на обработку персональных данных.
          </Text>
          <Text size="sm" ta="center">
            Нет аккаунта?{' '}
            <Anchor component={Link} to="/register">
              Зарегистрироваться
            </Anchor>
          </Text>
        </Stack>
      </form>
    </AuthCard>
  )
}
