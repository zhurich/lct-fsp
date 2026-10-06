import { Alert, Badge, Button, Group, Paper, Rating, Select, Stack, Text, Textarea, TextInput, Title } from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type ChallengeAnswer, type EmployerChallenge } from '../api'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'
import { formatDate, toOptions, useReference } from '../reference'

const KEY = ['employer-challenges']

export default function EmployerChallengesPage() {
  const queryClient = useQueryClient()
  const { data: reference, specName } = useReference()
  const challenges = useQuery({ queryKey: KEY, queryFn: () => api<EmployerChallenge[]>('/employer/challenges') })
  const [creating, setCreating] = useState(false)
  const [opened, setOpened] = useState<number | null>(null)
  const form = useForm({
    initialValues: { title: '', text: '', specialization: null as string | null },
    validate: {
      title: (value) => (value.trim() ? null : 'Укажите название'),
      text: (value) => (value.trim().length >= 20 ? null : 'Опишите задание подробнее'),
      specialization: (value) => (value ? null : 'Выберите специализацию'),
    },
  })
  const create = useMutation({
    mutationFn: (values: typeof form.values) => api('/employer/challenges', { method: 'POST', body: values }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: KEY })
      notifyOk('Задание опубликовано')
      form.reset()
      setCreating(false)
    },
    onError: notifyError,
  })
  const toggle = useMutation({
    mutationFn: (challenge: EmployerChallenge) =>
      api(`/employer/challenges/${challenge.id}`, { method: 'PUT', body: { ...challenge, is_open: !challenge.is_open } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
    onError: notifyError,
  })

  if (!challenges.data) return <Pending queries={[challenges]} />
  const showForm = creating || challenges.data.length === 0

  return (
    <Stack maw={860}>
      <Group justify="space-between">
        <div>
          <Title order={2}>Задания для кандидатов</Title>
          <Text c="dimmed" size="sm">
            Дайте короткую задачу из практики команды. Ответы приходят обезличенно, с подтверждённым грейдом автора —
            это свежий сигнал о кандидатах до приглашения.
          </Text>
        </div>
        {!showForm && <Button onClick={() => setCreating(true)}>Новое задание</Button>}
      </Group>

      {showForm && (
        <Paper withBorder p="lg">
          <form onSubmit={form.onSubmit((values) => create.mutate(values))}>
            <Stack>
              <Title order={4}>Новое задание</Title>
              <TextInput label="Название" placeholder="Например, медленный отчёт" {...form.getInputProps('title')} />
              <Textarea
                label="Условие"
                description="Задача на 10–15 минут: решить или предложить подход"
                autosize
                minRows={4}
                {...form.getInputProps('text')}
              />
              <Select
                label="Кому показывать"
                placeholder="Специализация"
                data={toOptions(reference?.specializations)}
                {...form.getInputProps('specialization')}
              />
              <Group>
                <Button type="submit" loading={create.isPending}>
                  Опубликовать
                </Button>
                {challenges.data.length > 0 && (
                  <Button variant="subtle" color="gray" onClick={() => setCreating(false)}>
                    Отмена
                  </Button>
                )}
              </Group>
            </Stack>
          </form>
        </Paper>
      )}

      {challenges.data.map((challenge) => (
        <Paper withBorder p="lg" key={challenge.id}>
          <Stack gap="sm">
            <Group justify="space-between" align="flex-start">
              <div>
                <Group gap="xs">
                  <Title order={4}>{challenge.title}</Title>
                  {!challenge.is_open && <Badge color="gray">Закрыто</Badge>}
                  {challenge.answers_unrated > 0 && <Badge color="blue">Без оценки: {challenge.answers_unrated}</Badge>}
                </Group>
                <Text size="sm" c="dimmed">
                  {specName(challenge.specialization)} · от {formatDate(challenge.created_at)}
                </Text>
              </div>
              <Group gap="xs">
                <Button variant="default" size="xs" disabled={toggle.isPending} onClick={() => toggle.mutate(challenge)}>
                  {challenge.is_open ? 'Закрыть' : 'Открыть'}
                </Button>
                <Button
                  variant="light"
                  size="xs"
                  disabled={challenge.answers_total === 0}
                  onClick={() => setOpened(opened === challenge.id ? null : challenge.id)}
                >
                  Ответы: {challenge.answers_total}
                </Button>
              </Group>
            </Group>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }} lineClamp={opened === challenge.id ? undefined : 2}>
              {challenge.text}
            </Text>
            {opened === challenge.id && <Answers challengeId={challenge.id} />}
          </Stack>
        </Paper>
      ))}
      {challenges.data.length === 0 && !showForm && <Alert color="gray">Заданий пока нет.</Alert>}
    </Stack>
  )
}

function Answers({ challengeId }: { challengeId: number }) {
  const queryClient = useQueryClient()
  const { gradeName } = useReference()
  const key = ['challenge-answers', challengeId]
  const answers = useQuery({
    queryKey: key,
    queryFn: () => api<ChallengeAnswer[]>(`/employer/challenges/${challengeId}/answers`),
  })
  const rate = useMutation({
    mutationFn: ({ id, rating }: { id: number; rating: number }) =>
      api(`/employer/answers/${id}/rating`, { method: 'PUT', body: { rating } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key })
      queryClient.invalidateQueries({ queryKey: KEY })
    },
    onError: notifyError,
  })

  if (!answers.data) return <Pending queries={[answers]} />
  return (
    <Stack gap="sm">
      {answers.data.map((answer) => (
        <Paper withBorder p="md" key={answer.id} bg="gray.0">
          <Stack gap={6}>
            <Group justify="space-between">
              <Text fw={500}>
                Кандидат №{answer.candidate_id}
                {answer.grade
                  ? ` · ${gradeName(answer.grade)}, балл теста ${Math.round((answer.test_score ?? 0) * 100)}`
                  : ' · категория не подтверждена'}
              </Text>
              <Rating value={answer.rating ?? 0} onChange={(rating) => rate.mutate({ id: answer.id, rating })} />
            </Group>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
              {answer.text}
            </Text>
            <Text size="xs" c="dimmed">
              {formatDate(answer.created_at)}
              {answer.in_bank
                ? ` · найдите кандидата №${answer.candidate_id} в банке или подборке, чтобы пригласить`
                : ' · профиль не опубликован, пригласить пока нельзя'}
            </Text>
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}
