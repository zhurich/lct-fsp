import { Button, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { api } from '../api'
import { signedOut, useMe } from '../auth'
import { notifyError } from '../notify'
import { formatDate } from '../reference'

/** Отзыв согласия на обработку данных: удаляет учётную запись. `deleted` — что именно будет удалено. */
export default function ConsentSection({ deleted }: { deleted: string }) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { data: user } = useMe()
  const remove = useMutation({
    mutationFn: () => api('/auth/me', { method: 'DELETE' }),
    onSuccess: () => {
      signedOut(queryClient)
      navigate('/login')
    },
    onError: notifyError,
  })
  if (!user) return null

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Title order={4}>Согласие на обработку данных</Title>
        <Text size="sm">
          Согласие на обработку персональных данных дано {formatDate(user.consent_at)} при регистрации. Его можно
          отозвать: {deleted} будут удалены без возможности восстановления.
        </Text>
        <Group>
          <Button
            color="red"
            variant="light"
            loading={remove.isPending}
            onClick={() =>
              window.confirm('Удалить учётную запись и все данные? Это действие нельзя отменить.') && remove.mutate()
            }
          >
            Отозвать согласие и удалить учётную запись
          </Button>
        </Group>
      </Stack>
    </Paper>
  )
}
