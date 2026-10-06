import { Alert, Badge, Button, Group, Modal, Paper, Select, SimpleGrid, Stack, Table, Text, Textarea, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type CandidateVacancy, type MyApplication } from '../api'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'
import { formatDate, formatSalary, INVITATION_STATUS, toOptions, useReference } from '../reference'

export default function VacanciesPage() {
  const queryClient = useQueryClient()
  const { data: reference, specName, gradeName, formatName } = useReference()
  const [specialization, setSpecialization] = useState<string | null>(null)
  const [grade, setGrade] = useState<string | null>(null)
  const [target, setTarget] = useState<CandidateVacancy | null>(null)
  const [message, setMessage] = useState('')

  const vacancies = useQuery({
    queryKey: ['vacancies', specialization, grade],
    queryFn: () => {
      const params = new URLSearchParams()
      if (specialization) params.set('specialization', specialization)
      if (grade) params.set('grade', grade)
      return api<CandidateVacancy[]>(`/candidate/vacancies?${params}`)
    },
  })
  const applications = useQuery({
    queryKey: ['applications'],
    queryFn: () => api<MyApplication[]>('/candidate/applications'),
  })
  const apply = useMutation({
    mutationFn: () => api(`/candidate/vacancies/${target!.id}/apply`, { method: 'POST', body: { message } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['vacancies'] })
      queryClient.invalidateQueries({ queryKey: ['applications'] })
      notifyOk('Отклик отправлен: работодатель видит вашу категорию и контакты')
      setTarget(null)
      setMessage('')
    },
    onError: notifyError,
  })

  return (
    <Stack maw={860}>
      <div>
        <Title order={2}>Вакансии</Title>
        <Text c="dimmed" size="sm">
          Можно не ждать приглашения и откликнуться самому. Зарплата указана в каждой вакансии; подходящие вашей
          категории показаны первыми.
        </Text>
      </div>

      {applications.data && applications.data.length > 0 && (
        <Paper withBorder p="lg">
          <Stack gap="sm">
            <Title order={4}>Мои отклики</Title>
            <Table>
              <Table.Tbody>
                {applications.data.map((item) => (
                  <Table.Tr key={item.id}>
                    <Table.Td>{item.title}</Table.Td>
                    <Table.Td>{item.company_name}</Table.Td>
                    <Table.Td>{formatDate(item.created_at)}</Table.Td>
                    <Table.Td>
                      <Badge color={INVITATION_STATUS[item.status].color} variant="light">
                        {INVITATION_STATUS[item.status].label}
                      </Badge>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        </Paper>
      )}

      <Paper withBorder p="lg">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select
            label="Специализация"
            placeholder="Любая"
            clearable
            data={toOptions(reference?.specializations)}
            value={specialization}
            onChange={setSpecialization}
          />
          <Select label="Грейд" placeholder="Любой" clearable data={toOptions(reference?.grades)} value={grade} onChange={setGrade} />
        </SimpleGrid>
      </Paper>

      {!vacancies.data ? (
        <Pending queries={[vacancies]} />
      ) : (
        vacancies.data.length === 0 && (
          <Alert color="gray" title="Открытых вакансий нет">
            Попробуйте изменить фильтры или загляните позже.
          </Alert>
        )
      )}
      {vacancies.data?.map((vacancy) => (
        <Paper withBorder p="lg" key={vacancy.id}>
          <Stack gap="sm">
            <Group justify="space-between" align="flex-start">
              <div>
                <Group gap="xs">
                  <Title order={4}>{vacancy.title}</Title>
                  {vacancy.fits_category && (
                    <Badge color="green" variant="light">
                      Ваша категория
                    </Badge>
                  )}
                </Group>
                <Text size="sm" c="dimmed">
                  {[
                    vacancy.company_name,
                    vacancy.company_industry,
                    `${specName(vacancy.specialization)} · ${gradeName(vacancy.grade)}`,
                    vacancy.work_formats.map(formatName).join(', '),
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </Text>
              </div>
              {vacancy.application_status ? (
                <Badge color={INVITATION_STATUS[vacancy.application_status].color} variant="light" size="lg">
                  Отклик: {INVITATION_STATUS[vacancy.application_status].label.toLowerCase()}
                </Badge>
              ) : (
                <Button onClick={() => setTarget(vacancy)}>Откликнуться</Button>
              )}
            </Group>
            <Text fw={600} size="lg">
              {formatSalary(vacancy.salary_from, vacancy.salary_to)}
            </Text>
            {vacancy.stack.length > 0 && (
              <Group gap={6}>
                {vacancy.stack.map((item) => (
                  <Badge key={item} variant="default" tt="none">
                    {item}
                  </Badge>
                ))}
              </Group>
            )}
            <Text style={{ whiteSpace: 'pre-wrap' }}>{vacancy.description}</Text>
          </Stack>
        </Paper>
      ))}

      <Modal opened={target !== null} onClose={() => setTarget(null)} title={target && `Отклик: ${target.title}`} size="lg">
        <Stack>
          <Text size="sm" c="dimmed">
            Работодатель увидит вашу подтверждённую категорию, балл теста, стек и контакты из профиля.
          </Text>
          <Textarea
            label="Сообщение работодателю"
            description="Необязательно"
            autosize
            minRows={3}
            value={message}
            onChange={(event) => setMessage(event.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setTarget(null)}>
              Отмена
            </Button>
            <Button loading={apply.isPending} onClick={() => apply.mutate()}>
              Отправить отклик
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  )
}
