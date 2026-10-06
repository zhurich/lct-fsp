import { Alert, Badge, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'

import { api, type EmployerInvitation } from '../api'
import Pending from '../components/Pending'
import { formatDate, formatSalary, INVITATION_STATUS, useReference } from '../reference'

export default function EmployerInvitationsPage() {
  const { specName, gradeName } = useReference()
  const invitations = useQuery({
    queryKey: ['employer-invitations'],
    queryFn: () => api<EmployerInvitation[]>('/employer/invitations'),
  })

  if (!invitations.data) return <Pending queries={[invitations]} />

  return (
    <Stack maw={860}>
      <Title order={2}>Приглашения</Title>
      {invitations.data.length === 0 && (
        <Alert color="gray" title="Вы ещё никого не пригласили">
          Найдите подходящих специалистов в разделе «Кандидаты» и отправьте им предложение.
        </Alert>
      )}
      {invitations.data.map((invitation) => (
        <Paper withBorder p="lg" key={invitation.id}>
          <Stack gap="sm">
            <Group justify="space-between" align="flex-start">
              <div>
                <Title order={4}>{invitation.title}</Title>
                <Text size="sm" c="dimmed">
                  {[
                    `Кандидат №${invitation.candidate_id}`,
                    invitation.specialization &&
                      `${specName(invitation.specialization)} · ${gradeName(invitation.grade)}`,
                    formatSalary(invitation.salary_from, invitation.salary_to),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </Text>
              </div>
              <Badge color={INVITATION_STATUS[invitation.status].color} variant="light" size="lg">
                {INVITATION_STATUS[invitation.status].label}
              </Badge>
            </Group>
            <Text style={{ whiteSpace: 'pre-wrap' }} lineClamp={4}>
              {invitation.message}
            </Text>
            {invitation.contacts ? (
              <Alert color="green" title="Кандидат принял приглашение — контакты открыты">
                {[
                  invitation.contacts.full_name,
                  invitation.contacts.email,
                  invitation.contacts.phone,
                  invitation.contacts.telegram,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </Alert>
            ) : (
              invitation.status !== 'declined' && (
                <Text size="sm" c="dimmed">
                  Контакты кандидата откроются, когда он примет приглашение.
                </Text>
              )
            )}
            <Text size="sm" c="dimmed">
              Отправлено {formatDate(invitation.created_at)}
              {invitation.responded_at && ` · ответ ${formatDate(invitation.responded_at)}`}
            </Text>
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}
