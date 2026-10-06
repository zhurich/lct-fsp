import { Alert, Badge, Button, Group, Paper, Rating, Stack, Text, Textarea, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type CandidateChallenge, type MyAnswer } from '../api'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'
import { formatDate } from '../reference'

const MIN_LENGTH = 50

export default function ChallengesPage() {
  const challenges = useQuery({
    queryKey: ['challenges'],
    queryFn: () => api<CandidateChallenge[]>('/candidate/challenges'),
  })
  const answers = useQuery({ queryKey: ['answers'], queryFn: () => api<MyAnswer[]>('/candidate/answers') })

  if (!challenges.data || !answers.data) return <Pending queries={[challenges, answers]} />

  return (
    <Stack maw={860}>
      <div>
        <Title order={2}>Задания от работодателей</Title>
        <Text c="dimmed" size="sm">
          Короткие задачи из практики компаний по вашей специализации. Решите или опишите подход: ответ обновляет
          актуальность профиля и поднимает вас в подборках, а работодатель может пригласить автора удачного решения.
        </Text>
      </div>

      {challenges.data.length === 0 && (
        <Alert color="gray" title="Новых заданий пока нет">
          Задания подбираются по специализации из вашей категории или профиля. Загляните позже.
        </Alert>
      )}
      {challenges.data.map((challenge) => (
        <ChallengeCard key={challenge.id} challenge={challenge} />
      ))}

      {answers.data.length > 0 && <Title order={4}>Мои ответы</Title>}
      {answers.data.map((answer) => (
        <Paper withBorder p="lg" key={answer.id}>
          <Stack gap="xs">
            <Group justify="space-between">
              <Text fw={500}>
                {answer.challenge_title} · {answer.company_name}
              </Text>
              {answer.rating ? (
                <Rating value={answer.rating} readOnly />
              ) : (
                <Badge color="gray" variant="light">
                  Ждёт оценки
                </Badge>
              )}
            </Group>
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }} lineClamp={4}>
              {answer.text}
            </Text>
            <Text size="xs" c="dimmed">
              {formatDate(answer.created_at)}
            </Text>
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}

function ChallengeCard({ challenge }: { challenge: CandidateChallenge }) {
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const send = useMutation({
    mutationFn: () => api(`/candidate/challenges/${challenge.id}/answer`, { method: 'POST', body: { text } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['challenges'] })
      queryClient.invalidateQueries({ queryKey: ['answers'] })
      notifyOk('Ответ отправлен работодателю')
    },
    onError: notifyError,
  })
  const left = MIN_LENGTH - text.trim().length

  return (
    <Paper withBorder p="lg">
      <Stack gap="sm">
        <div>
          <Title order={4}>{challenge.title}</Title>
          <Text size="sm" c="dimmed">
            {challenge.company_name} · {formatDate(challenge.created_at)}
          </Text>
        </div>
        <Text style={{ whiteSpace: 'pre-wrap' }}>{challenge.text}</Text>
        <Textarea
          label="Ваше решение или подход"
          autosize
          minRows={4}
          value={text}
          onChange={(event) => setText(event.currentTarget.value)}
        />
        <Group>
          <Button loading={send.isPending} disabled={left > 0} onClick={() => send.mutate()}>
            Отправить ответ
          </Button>
          {left > 0 && text.length > 0 && (
            <Text size="sm" c="dimmed">
              Ещё минимум {left} симв.
            </Text>
          )}
        </Group>
      </Stack>
    </Paper>
  )
}
