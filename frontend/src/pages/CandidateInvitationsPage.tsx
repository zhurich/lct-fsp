import { Alert, Anchor, Badge, Button, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type CandidateInvitation } from '../api'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'
import { formatDate, formatSalary, INVITATION_STATUS } from '../reference'

const KEY = ['candidate-invitations']

export default function CandidateInvitationsPage() {
  const queryClient = useQueryClient()
  const invitations = useQuery({
    queryKey: KEY,
    queryFn: () => api<CandidateInvitation[]>('/candidate/invitations'),
  })
  const respond = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'accept' | 'decline' }) =>
      api<CandidateInvitation>(`/candidate/invitations/${id}/${action}`, { method: 'POST' }),
    onSuccess: (updated) => {
      queryClient.setQueryData<CandidateInvitation[]>(KEY, (list = []) =>
        list.map((item) => (item.id === updated.id ? updated : item)),
      )
      notifyOk(
        updated.status === 'accepted'
          ? 'Приглашение принято: работодатель получил ваши контакты'
          : 'Приглашение отклонено',
      )
    },
    onError: notifyError,
  })

  if (!invitations.data) return <Pending queries={[invitations]} />

  return (
    <Stack maw={860}>
      <Title order={2}>Приглашения</Title>
      {invitations.data.length === 0 && (
        <Alert color="gray" title="Приглашений пока нет">
          Работодатели находят кандидатов по категории. Пройдите тест и разрешите показывать профиль — и
          предложения с зарплатной вилкой будут приходить сюда.
        </Alert>
      )}
      {invitations.data.map((invitation) => {
        const pending = invitation.status === 'sent' || invitation.status === 'viewed'
        return (
          <Paper withBorder p="lg" key={invitation.id}>
            <Stack gap="sm">
              <Group justify="space-between" align="flex-start">
                <div>
                  <Title order={4}>{invitation.title}</Title>
                  <Text size="sm" c="dimmed">
                    {[invitation.company_name, invitation.company_industry].filter(Boolean).join(' · ')}
                  </Text>
                </div>
                {invitation.status === 'sent' ? (
                  <Badge color="blue">Новое</Badge>
                ) : (
                  !pending && (
                    <Badge color={INVITATION_STATUS[invitation.status].color} variant="light">
                      {INVITATION_STATUS[invitation.status].label}
                    </Badge>
                  )
                )}
              </Group>
              <Text fw={600} size="lg">
                {formatSalary(invitation.salary_from, invitation.salary_to)}
              </Text>
              <Text style={{ whiteSpace: 'pre-wrap' }}>{invitation.message}</Text>
              {invitation.company_description && (
                <Text size="sm" c="dimmed" style={{ whiteSpace: 'pre-wrap' }}>
                  О компании: {invitation.company_description}
                </Text>
              )}
              <Text size="sm">
                Связь с работодателем: {invitation.contact}
                {invitation.company_website && (
                  <>
                    {' · '}
                    <Anchor href={invitation.company_website} target="_blank" rel="noreferrer">
                      {invitation.company_website}
                    </Anchor>
                  </>
                )}
              </Text>
              <Group justify="space-between">
                <Text size="sm" c="dimmed">
                  Получено {formatDate(invitation.created_at)}
                </Text>
                {pending && (
                  <Group gap="sm">
                    <Button
                      variant="default"
                      disabled={respond.isPending}
                      onClick={() => respond.mutate({ id: invitation.id, action: 'decline' })}
                    >
                      Отклонить
                    </Button>
                    <Button
                      disabled={respond.isPending}
                      onClick={() => respond.mutate({ id: invitation.id, action: 'accept' })}
                    >
                      Принять и открыть контакты
                    </Button>
                  </Group>
                )}
              </Group>
            </Stack>
          </Paper>
        )
      })}
    </Stack>
  )
}
