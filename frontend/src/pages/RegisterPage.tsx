import {
  Alert,
  Anchor,
  Button,
  Checkbox,
  PasswordInput,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { api, type Role } from '../api'
import AuthCard from '../components/AuthCard'
import ResendVerification from '../components/ResendVerification'

export default function RegisterPage() {
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)
  // Демо-режим стенда: почта подтверждена сразу, письма нет.
  const [ready, setReady] = useState<string | null>(null)
  const form = useForm({
    initialValues: { role: 'candidate' as Role, email: '', password: '', consent: false },
    validate: {
      password: (value) => (value.length < 8 ? 'Не короче 8 символов' : null),
      consent: (value) => (value ? null : 'Без согласия регистрация невозможна'),
    },
  })

  const submit = form.onSubmit(async (values) => {
    setError(null)
    setLoading(true)
    try {
      const result = await api<{ message: string; verified: boolean }>('/auth/register', {
        method: 'POST',
        body: values,
      })
      if (result.verified) setReady(result.message)
      else setSentTo(values.email)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось зарегистрироваться')
    } finally {
      setLoading(false)
    }
  })

  if (ready) {
    return (
      <AuthCard title="Регистрация завершена">
        <Text>{ready}.</Text>
        <Button component={Link} to="/login">
          Перейти ко входу
        </Button>
      </AuthCard>
    )
  }
  if (sentTo) {
    return (
      <AuthCard title="Проверьте почту">
        <Text>
          Мы отправили письмо на <b>{sentTo}</b>. Перейдите по ссылке из него, чтобы подтвердить адрес, и
          затем войдите.
        </Text>
        <Text size="sm" c="dimmed">
          Письмо не пришло? Проверьте папку «Спам» или запросите его повторно — не чаще раза в минуту.
        </Text>
        <ResendVerification email={sentTo} />
        <Button component={Link} to="/login" variant="light">
          Перейти ко входу
        </Button>
      </AuthCard>
    )
  }

  return (
    <AuthCard title="Регистрация">
      <form onSubmit={submit}>
        <Stack>
          {error && <Alert color="red">{error}</Alert>}
          <SegmentedControl
            fullWidth
            data={[
              { value: 'candidate', label: 'Я ищу работу' },
              { value: 'employer', label: 'Я ищу специалистов' },
            ]}
            {...form.getInputProps('role')}
          />
          <TextInput label="Электронная почта" type="email" required {...form.getInputProps('email')} />
          <PasswordInput
            label="Пароль"
            description="Не короче 8 символов"
            required
            {...form.getInputProps('password')}
          />
          <Checkbox
            label="Согласен на обработку персональных данных"
            {...form.getInputProps('consent', { type: 'checkbox' })}
          />
          <Button type="submit" loading={loading}>
            Зарегистрироваться
          </Button>
          <Text size="sm" ta="center">
            Уже есть аккаунт?{' '}
            <Anchor component={Link} to="/login">
              Войти
            </Anchor>
          </Text>
        </Stack>
      </form>
    </AuthCard>
  )
}
