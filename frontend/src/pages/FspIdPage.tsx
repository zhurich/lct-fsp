import { Alert, Anchor, Button, Center, Paper, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { useForm } from '@mantine/form'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import { api } from '../api'

type DemoAccounts = { password: string; accounts: { email: string; note: string }[] }

/**
 * Страница входа демонстрационного ФСП ID — мок внешнего провайдера (в целевой схеме это Keycloak ФСП).
 * Платформа сюда перенаправляет и получает пользователя обратно с одноразовым кодом, как по OpenID Connect.
 */
export default function FspIdPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const demo = useQuery({ queryKey: ['fsp-id-accounts'], queryFn: () => api<DemoAccounts>('/fsp-id/accounts') })
  const form = useForm({ initialValues: { email: '', password: '' } })
  const state = params.get('state')
  const redirect = params.get('redirect_uri') ?? ''
  // Возврат — только на страницу этой же платформы: чужой адрес в параметре не принимается.
  const valid = Boolean(state) && redirect.startsWith('/') && !redirect.startsWith('//')

  const submit = form.onSubmit(async (values) => {
    setError(null)
    setLoading(true)
    try {
      const { code } = await api<{ code: string }>('/fsp-id/login', { method: 'POST', body: values })
      navigate(`${redirect}?${new URLSearchParams({ code, state: state! })}`, { replace: true })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось войти')
      setLoading(false)
    }
  })

  return (
    <Center mih="100vh" p="md" bg="gray.1">
      <Paper withBorder p="xl" w="100%" maw={440}>
        <Stack>
          <div>
            <Text className="fsp-overline" c="dimmed" mb={8}>
              Демонстрационный стенд
            </Text>
            <Title order={2}>ФСП ID</Title>
            <Text size="sm" c="dimmed" mt={4}>
              Единый аккаунт участника Федерации спортивного программирования. Сервис «ФСП Карьера» получит вашу
              почту и сведения о достижениях.
            </Text>
          </div>
          {!valid ? (
            <Alert color="gray" title="Запрос на вход повреждён">
              Вернитесь на платформу и начните вход заново. <Anchor href="/login">Ко входу</Anchor>
            </Alert>
          ) : (
            <form onSubmit={submit}>
              <Stack>
                {error && <Alert color="red">{error}</Alert>}
                <TextInput label="Электронная почта" type="email" required {...form.getInputProps('email')} />
                <PasswordInput label="Пароль ФСП ID" required {...form.getInputProps('password')} />
                <Button type="submit" loading={loading}>
                  Войти и вернуться на платформу
                </Button>
              </Stack>
            </form>
          )}
          {demo.data && valid && (
            <Alert color="gray" title="Как войти на стенде">
              <Stack gap={6}>
                <Text size="sm">
                  Подойдёт любая почта, пароль у всех один — <b>{demo.data.password}</b>. Одна и та же почта всегда
                  даёт одного участника. Готовые участники:
                </Text>
                {demo.data.accounts.map((account) => (
                  <Text size="sm" key={account.email}>
                    <Anchor
                      component="button"
                      type="button"
                      onClick={() => form.setValues({ email: account.email, password: demo.data.password })}
                    >
                      {account.email}
                    </Anchor>{' '}
                    — {account.note.toLowerCase()}
                  </Text>
                ))}
              </Stack>
            </Alert>
          )}
        </Stack>
      </Paper>
    </Center>
  )
}
