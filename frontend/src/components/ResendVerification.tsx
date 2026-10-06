import { Button, Group, Text } from '@mantine/core'
import { useMutation } from '@tanstack/react-query'

import { api } from '../api'

/** Повторная отправка письма со ссылкой подтверждения на указанный адрес. */
export default function ResendVerification({ email }: { email: string }) {
  const resend = useMutation({
    mutationFn: () => api<{ message: string }>('/auth/resend-verification', { method: 'POST', body: { email } }),
  })
  return (
    <Group gap="sm">
      <Button variant="default" size="xs" loading={resend.isPending} onClick={() => resend.mutate()}>
        Отправить письмо ещё раз
      </Button>
      {resend.isSuccess && (
        <Text size="sm" c="dimmed">
          Письмо отправлено повторно.
        </Text>
      )}
      {resend.error && (
        <Text size="sm" c="dimmed">
          {resend.error.message}
        </Text>
      )}
    </Group>
  )
}
