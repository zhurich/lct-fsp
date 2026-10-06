import { Alert, Badge, Button, Group, List, Paper, Stack, Text, Title } from '@mantine/core'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api, type CandidateProfileFull } from '../api'
import { notifyError, notifyOk } from '../notify'
import { FSP_LEVEL } from '../reference'

/** Привязка ФСП ID и достижения из реестра. Отсутствие привязки — обычное состояние, а не недостаток. */
export default function FspSection({ profile }: { profile: CandidateProfileFull }) {
  const queryClient = useQueryClient()
  // Владение аккаунтом подтверждается входом в ФСП ID: платформа перенаправляет на его страницу входа.
  const link = useMutation({
    mutationFn: () => api<{ url: string }>('/candidate/fsp/start'),
    onSuccess: ({ url }) => window.location.assign(url),
    onError: notifyError,
  })
  const change = useMutation({
    mutationFn: (action: 'refresh' | 'unlink') =>
      api<CandidateProfileFull>(
        action === 'refresh' ? '/candidate/fsp/refresh' : '/candidate/fsp',
        { method: action === 'refresh' ? 'POST' : 'DELETE' },
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(['candidate-profile'], saved)
      notifyOk(saved.fsp_id ? 'Достижения обновлены из реестра' : 'ФСП ID отвязан')
    },
    onError: notifyError,
  })

  return (
    <Paper withBorder p="lg">
      <Stack>
        <Group gap="sm">
          <Title order={4}>Достижения ФСП</Title>
          {profile.fsp_id && <Badge color="dark">{profile.fsp_id}</Badge>}
          {profile.fsp_rank && (
            <Badge variant="light" tt="none">
              {profile.fsp_rank}
            </Badge>
          )}
        </Group>
        {!profile.fsp_id ? (
          <>
            <Text size="sm" c="dimmed">
              Если вы участвовали в соревнованиях Федерации спортивного программирования, привяжите ФСП ID:
              подтверждённые результаты поднимут вас в подборках работодателей среди кандидатов вашей категории.
              На грейд они не влияют — его подтверждает только тест. Без привязки профиль участвует в подборе на
              общих основаниях.
            </Text>
            <Group>
              <Button loading={link.isPending} onClick={() => link.mutate()}>
                Привязать через ФСП ID
              </Button>
            </Group>
          </>
        ) : (
          <>
            {profile.fsp_achievements.length === 0 ? (
              <Alert color="gray">
                В реестре ФСП пока нет ваших результатов. Это не влияет на профиль: когда результаты появятся,
                они подтянутся при следующей синхронизации.
              </Alert>
            ) : (
              <List size="sm">
                {profile.fsp_achievements.map((item, index) => (
                  <List.Item key={index}>
                    {item.place ? `${item.place} место` : 'Участие'} · {item.event} (
                    {FSP_LEVEL[item.level] ?? item.level}), {item.discipline.toLowerCase()},{' '}
                    {new Date(item.date).getFullYear()}
                    {item.team && ', командный результат'}
                  </List.Item>
                ))}
              </List>
            )}
            <Group>
              <Button variant="default" size="xs" loading={change.isPending} onClick={() => change.mutate('refresh')}>
                Обновить из реестра
              </Button>
              <Button
                variant="subtle"
                color="red"
                size="xs"
                disabled={change.isPending}
                onClick={() => change.mutate('unlink')}
              >
                Отвязать
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Paper>
  )
}
