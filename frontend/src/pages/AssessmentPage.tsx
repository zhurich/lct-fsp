import {
  Alert,
  Badge,
  Button,
  Code,
  Group,
  Paper,
  Progress,
  Radio,
  Select,
  SimpleGrid,
  Stack,
  Table,
  TagsInput,
  Text,
  Title,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type AssessmentState, type CandidateProfile } from '../api'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'
import { formatDate, toOptions, useReference } from '../reference'

const KEY = ['assessment']
// Наименьшая высота карточки, подогнана под типичное задание (вопрос, код в 5–6 строк, четыре варианта).
const QUESTION_CARD_MIN_HEIGHT = 400
type Active = NonNullable<AssessmentState['active']>

export default function AssessmentPage() {
  const state = useQuery({ queryKey: KEY, queryFn: () => api<AssessmentState>('/candidate/assessment') })
  const profile = useQuery({
    queryKey: ['candidate-profile'],
    queryFn: () => api<CandidateProfile>('/candidate/profile'),
  })

  if (!state.data || !profile.data) return <Pending queries={[state, profile]} />

  return (
    <Stack maw={860}>
      <Title order={2}>Тест и категория</Title>
      {state.data.active ? (
        <TestForm attempt={state.data.active} />
      ) : (
        <>
          <CategoryCard state={state.data} profile={profile.data} />
          <StartForm state={state.data} profile={profile.data} />
          <History state={state.data} />
          <DemoReset state={state.data} />
        </>
      )}
    </Stack>
  )
}

function CategoryCard({ state, profile }: { state: AssessmentState; profile: CandidateProfile }) {
  const queryClient = useQueryClient()
  const { specName, gradeName } = useReference()
  const publish = useMutation({
    mutationFn: () =>
      api<CandidateProfile>('/candidate/profile', { method: 'PUT', body: { ...profile, is_published: true } }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['candidate-profile'], saved)
      notifyOk('Профиль виден работодателям')
    },
    onError: notifyError,
  })
  const { category } = state

  if (!category) {
    return (
      <Alert title="Категория ещё не присвоена">
        Работодатели ищут кандидатов по категории — связке специализации и грейда. Она присваивается по
        результату теста, а не по резюме: выберите направление и грейд ниже и пройдите тест.
        {state.history.length > 0 &&
          ' Пока грейд не подтверждён, опубликованный профиль показывается работодателям с пометкой об этом — ниже кандидатов с категорией.'}
      </Alert>
    )
  }
  return (
    <Paper withBorder p="lg">
      <Stack gap="sm">
        <Text size="sm" c="dimmed">
          Ваша категория
        </Text>
        <Group gap="sm">
          <Title order={3}>
            {specName(category.specialization)} · {gradeName(category.grade)}
          </Title>
          <Badge color="green" variant="light">
            Балл теста: {Math.round(category.score * 100)} из 100
          </Badge>
        </Group>
        <Text size="sm" c="dimmed">
          Подтверждена {formatDate(category.assigned_at)}
        </Text>
        {category.upgrade_offer && (
          <Alert color="green" title="Результат выше вашего грейда">
            Вы прошли тест с запасом. Можно один раз, не дожидаясь срока смены категории, сдать тест на
            следующий грейд — форма ниже. Если не получится, текущая категория сохранится.
          </Alert>
        )}
        {!profile.is_published && (
          <Alert color="yellow" title="Профиль скрыт от работодателей">
            <Stack gap="sm" align="flex-start">
              <Text size="sm">
                Чтобы получать приглашения, разрешите показывать профиль. Имя и контакты работодатель увидит
                только после того, как вы примете его приглашение.
              </Text>
              <Button size="xs" loading={publish.isPending} onClick={() => publish.mutate()}>
                Показывать профиль работодателям
              </Button>
            </Stack>
          </Alert>
        )}
      </Stack>
    </Paper>
  )
}

function StartForm({ state, profile }: { state: AssessmentState; profile: CandidateProfile }) {
  const queryClient = useQueryClient()
  const { data: reference, gradeName } = useReference()
  // Срок после провала считается по специализации: без выбранной специализации закрытых грейдов нет.
  const locksOf = (specialization: string | null) =>
    new Map(
      ((specialization && state.grades_by_specialization[specialization]) || []).map((item) => [
        item.grade,
        item.available_from,
      ]),
    )
  const resumeGrade = queryClient.getQueryData<string | null>(['resume-grade']) ?? null
  const initialSpecialization = state.category?.specialization ?? profile.specialization
  const form = useForm({
    initialValues: {
      specialization: initialSpecialization,
      // Грейд из загруженного резюме, если тест на него сейчас доступен.
      grade: resumeGrade && !locksOf(initialSpecialization).get(resumeGrade) ? resumeGrade : null,
      stack: profile.stack,
    },
    validate: {
      specialization: (value) => (value ? null : 'Выберите специализацию'),
      grade: (value) => (value ? null : 'Выберите грейд'),
    },
  })
  // Подсказка после провала: на какой грейд тянет результат.
  const lastFailed = state.history[0]?.status === 'failed' ? state.history[0] : null
  const start = useMutation({
    mutationFn: (values: typeof form.values) =>
      api<AssessmentState>('/candidate/assessment', { method: 'POST', body: values }),
    onSuccess: (next) => {
      queryClient.setQueryData(KEY, next)
      // Опрос обновил специализацию и стек в профиле.
      queryClient.invalidateQueries({ queryKey: ['candidate-profile'] })
    },
    onError: notifyError,
  })

  const lockedUntil = locksOf(form.values.specialization)
  const everyGrade = Object.values(state.grades_by_specialization).flat()
  if (everyGrade.every((item) => item.available_from)) {
    const soonest = everyGrade.map((item) => item.available_from!).sort()[0]
    return (
      <Alert color="gray" title="Новый тест пока недоступен">
        Сменить грейд или специализацию можно будет с {formatDate(soonest)}.
      </Alert>
    )
  }
  return (
    <Paper withBorder p="lg">
      <form onSubmit={form.onSubmit((values) => start.mutate(values))}>
        <Stack>
          <Title order={4}>{state.category ? 'Сменить категорию' : 'Опрос перед тестом'}</Title>
          {lastFailed?.estimated_grade && (
            <Text size="sm">
              По последнему тесту ваш результат соответствует грейду «{gradeName(lastFailed.estimated_grade)}» —
              тест на него доступен сразу.
            </Text>
          )}
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select
              label="Специализация"
              placeholder="Выберите направление"
              data={toOptions(reference?.specializations)}
              {...form.getInputProps('specialization')}
              onChange={(specialization) => {
                form.setFieldValue('specialization', specialization)
                // Выбранный грейд в новой специализации может быть закрыт после провала.
                if (form.values.grade && locksOf(specialization).get(form.values.grade)) {
                  form.setFieldValue('grade', null)
                }
              }}
            />
            <Select
              label="Предполагаемый грейд"
              placeholder="На какой уровень сдаёте"
              data={(reference?.grades ?? []).map((grade) => {
                const until = lockedUntil.get(grade.code)
                return {
                  value: grade.code,
                  label: until ? `${grade.name} — доступен с ${formatDate(until)}` : grade.name,
                  disabled: Boolean(until),
                }
              })}
              {...form.getInputProps('grade')}
            />
          </SimpleGrid>
          {form.values.grade && (
            <Text size="sm" c="dimmed">
              {gradeName(form.values.grade)}:{' '}
              {reference?.grades.find((grade) => grade.code === form.values.grade)?.description}
            </Text>
          )}
          <TagsInput
            label="Основной стек"
            data={reference?.skills}
            description="Введите технологию и нажмите Enter. По стеку работодатель уточняет подборку"
            {...form.getInputProps('stack')}
          />
          <Text size="sm" c="dimmed">
            Тест адаптивный и ограничен по времени, прервать его и начать заново нельзя. Если не пройдёте —
            сможете сразу сдать тест на грейд ниже.
          </Text>
          <Group>
            <Button type="submit" loading={start.isPending}>
              Начать тест
            </Button>
          </Group>
        </Stack>
      </form>
    </Paper>
  )
}

function TestForm({ attempt }: { attempt: Active }) {
  const queryClient = useQueryClient()
  const { specName, gradeName } = useReference()
  const [choice, setChoice] = useState<string | null>(null)
  const submit = useMutation({
    mutationFn: (answer: number | null) =>
      api<AssessmentState>(`/candidate/assessment/${attempt.id}/answer`, {
        method: 'POST',
        body: { position: attempt.position, answer },
      }),
    onSuccess: (next) => {
      setChoice(null)
      queryClient.setQueryData(KEY, next)
      if (next.active) return
      const result = next.history[0]
      const points = Math.round((result.score ?? 0) * 100)
      if (result.status === 'passed') {
        notifyOk(`Тест пройден, балл ${points} из 100. Категория присвоена`)
      } else {
        notifyError(new Error(`Тест на грейд «${gradeName(result.grade)}» не пройден, балл ${points} из 100`))
      }
    },
    onError: (error) => {
      notifyError(error)
      // Например, вышло время: состояние на сервере изменилось.
      queryClient.invalidateQueries({ queryKey: KEY })
    },
  })
  const deadline = new Date(attempt.expires_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  const { question } = attempt

  return (
    <Stack>
      <Alert title={`Тест: ${specName(attempt.specialization)} · ${gradeName(attempt.grade)}`}>
        {attempt.total} заданий по одному, вернуться к предыдущему нельзя. Сложность следующего задания
        зависит от ваших ответов. Завершите тест до {deadline} — позже попытка не засчитается.
      </Alert>
      {/* Карточка не ниже заданной высоты: кнопки не прыгают от задания к заданию. Длинное задание с кодом
          показывается целиком, без прокрутки, — карточка подрастает. */}
      <Paper withBorder p="lg" mih={{ sm: QUESTION_CARD_MIN_HEIGHT }} display="flex">
        <Stack gap="sm" style={{ flex: 1 }}>
          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              Задание {attempt.position} из {attempt.total}
            </Text>
            <Progress value={((attempt.position - 1) / attempt.total) * 100} w={160} aria-label="Прогресс теста" />
          </Group>
          <Stack gap="sm" style={{ flex: 1 }}>
            <Text fw={500}>{question.text}</Text>
            {question.code && <Code block>{question.code}</Code>}
            <Radio.Group value={choice} onChange={setChoice}>
              <Stack gap="xs">
                {question.options.map((option, index) => (
                  <Radio key={index} value={String(index)} label={option} />
                ))}
              </Stack>
            </Radio.Group>
          </Stack>
          <Group>
            <Button
              loading={submit.isPending}
              disabled={choice === null}
              onClick={() => submit.mutate(Number(choice))}
            >
              {attempt.position === attempt.total ? 'Ответить и завершить' : 'Ответить'}
            </Button>
            <Button variant="subtle" color="gray" disabled={submit.isPending} onClick={() => submit.mutate(null)}>
              Не знаю, пропустить
            </Button>
          </Group>
        </Stack>
      </Paper>
    </Stack>
  )
}

/** Стенд проверки: сроки пересдачи остаются видны, но попытки можно обнулить и пройти тест ещё раз. */
function DemoReset({ state }: { state: AssessmentState }) {
  const queryClient = useQueryClient()
  const reset = useMutation({
    mutationFn: () => api<AssessmentState>('/candidate/assessment/reset', { method: 'POST' }),
    onSuccess: (next) => {
      queryClient.setQueryData(KEY, next)
      notifyOk('Попытки сброшены, тест можно пройти заново')
    },
    onError: notifyError,
  })
  if (!state.demo_mode || (state.history.length === 0 && !state.category)) return null
  return (
    <Alert color="gray" title="Демо-режим стенда">
      <Stack gap="sm" align="flex-start">
        <Text size="sm">
          На рабочем стенде повторный тест ограничен сроками выше. Здесь попытки и категорию можно сбросить,
          чтобы пройти тест ещё раз и сравнить результаты.
        </Text>
        <Button
          size="xs"
          variant="default"
          loading={reset.isPending}
          onClick={() => window.confirm('Удалить все свои попытки и категорию?') && reset.mutate()}
        >
          Сбросить попытки и пройти заново
        </Button>
      </Stack>
    </Alert>
  )
}

function History({ state }: { state: AssessmentState }) {
  const { specName, gradeName } = useReference()
  if (state.history.length === 0) return null
  return (
    <Paper withBorder p="lg">
      <Stack>
        <Title order={4}>История тестов</Title>
        {/* На узком экране прокручивается сама таблица, а не вся страница. */}
        <Table.ScrollContainer minWidth={560}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Дата</Table.Th>
                <Table.Th>Специализация</Table.Th>
                <Table.Th>Тест на грейд</Table.Th>
                <Table.Th>Балл</Table.Th>
                <Table.Th>Соответствует</Table.Th>
                <Table.Th>Итог</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {state.history.map((attempt) => (
                <Table.Tr key={attempt.id}>
                  <Table.Td>{formatDate(attempt.finished_at ?? attempt.started_at)}</Table.Td>
                  <Table.Td>{specName(attempt.specialization)}</Table.Td>
                  <Table.Td>{gradeName(attempt.grade)}</Table.Td>
                  <Table.Td>{Math.round((attempt.score ?? 0) * 100)}</Table.Td>
                  <Table.Td>{attempt.estimated_grade ? gradeName(attempt.estimated_grade) : '—'}</Table.Td>
                  <Table.Td>
                    <Badge color={attempt.status === 'passed' ? 'green' : 'red'} variant="light">
                      {attempt.status === 'passed' ? 'Пройден' : 'Не пройден'}
                    </Badge>
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      </Stack>
    </Paper>
  )
}
