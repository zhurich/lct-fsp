import {
  Alert,
  Badge,
  Button,
  Group,
  Modal,
  MultiSelect,
  NumberInput,
  Paper,
  Select,
  SimpleGrid,
  Stack,
  TagsInput,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type EmployerVacancy, type VacancyApplication, type VacancyInput } from '../api'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'
import { formatDate, formatSalary, INVITATION_STATUS, toOptions, useReference } from '../reference'

const EMPTY: VacancyInput = {
  title: '',
  description: '',
  specialization: null,
  grade: null,
  stack: [],
  work_formats: [],
  salary_from: '',
  salary_to: '',
  is_open: true,
}

export default function EmployerVacanciesPage() {
  const { specName, gradeName } = useReference()
  const vacancies = useQuery({ queryKey: ['employer-vacancies'], queryFn: () => api<EmployerVacancy[]>('/employer/vacancies') })
  // null — форма закрыта, 'new' — создание, иначе — правка выбранной вакансии.
  const [editing, setEditing] = useState<EmployerVacancy | 'new' | null>(null)
  const [opened, setOpened] = useState<number | null>(null)

  if (!vacancies.data) return <Pending queries={[vacancies]} />

  return (
    <Stack maw={860}>
      <Group justify="space-between">
        <div>
          <Title order={2}>Вакансии</Title>
          <Text c="dimmed" size="sm">
            Классический сценарий: кандидаты с подтверждённой категорией откликаются сами.
          </Text>
        </div>
        <Button onClick={() => setEditing('new')}>Новая вакансия</Button>
      </Group>

      {vacancies.data.length === 0 && (
        <Alert color="gray" title="Вакансий пока нет">
          Опубликуйте вакансию, чтобы получать отклики. Зарплатная вилка обязательна — кандидат видит её сразу.
        </Alert>
      )}
      {vacancies.data.map((vacancy) => (
        <Paper withBorder p="lg" key={vacancy.id}>
          <Stack gap="sm">
            <Group justify="space-between" align="flex-start">
              <div>
                <Group gap="xs">
                  <Title order={4}>{vacancy.title}</Title>
                  {!vacancy.is_open && <Badge color="gray">Закрыта</Badge>}
                  {vacancy.applications_new > 0 && <Badge color="blue">Новых откликов: {vacancy.applications_new}</Badge>}
                </Group>
                <Text size="sm" c="dimmed">
                  {specName(vacancy.specialization)} · {gradeName(vacancy.grade)} ·{' '}
                  {formatSalary(vacancy.salary_from as number, vacancy.salary_to as number)} · от{' '}
                  {formatDate(vacancy.created_at)}
                </Text>
              </div>
              <Group gap="xs">
                <Button variant="default" size="xs" onClick={() => setEditing(vacancy)}>
                  Изменить
                </Button>
                <Button
                  variant="light"
                  size="xs"
                  disabled={vacancy.applications_total === 0}
                  onClick={() => setOpened(opened === vacancy.id ? null : vacancy.id)}
                >
                  Отклики: {vacancy.applications_total}
                </Button>
              </Group>
            </Group>
            {opened === vacancy.id && <Applications vacancyId={vacancy.id} />}
          </Stack>
        </Paper>
      ))}

      <Modal
        opened={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'Новая вакансия' : 'Изменить вакансию'}
        size="lg"
      >
        {editing && <VacancyForm vacancy={editing === 'new' ? undefined : editing} onDone={() => setEditing(null)} />}
      </Modal>
    </Stack>
  )
}

function Applications({ vacancyId }: { vacancyId: number }) {
  const queryClient = useQueryClient()
  const { gradeName } = useReference()
  const key = ['vacancy-applications', vacancyId]
  const applications = useQuery({
    queryKey: key,
    queryFn: async () => {
      const result = await api<VacancyApplication[]>(`/employer/vacancies/${vacancyId}/applications`)
      // Открытие списка пометило отклики просмотренными — обновляем счётчик новых.
      queryClient.invalidateQueries({ queryKey: ['employer-vacancies'] })
      return result
    },
  })
  const respond = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'accept' | 'decline' }) =>
      api(`/employer/applications/${id}/${action}`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
    onError: notifyError,
  })

  if (!applications.data) return <Pending queries={[applications]} />
  return (
    <Stack gap="sm">
      {applications.data.map((item) => (
        <Paper withBorder p="md" key={item.id} bg="gray.0">
          <Stack gap={6}>
            <Group justify="space-between">
              <Text fw={500}>
                {item.contacts.full_name || `Кандидат №${item.candidate_id}`} · {gradeName(item.grade)}, балл теста{' '}
                {Math.round(item.test_score * 100)}
              </Text>
              <Badge color={INVITATION_STATUS[item.status].color} variant="light">
                {item.status === 'sent' ? 'Новый' : INVITATION_STATUS[item.status].label}
              </Badge>
            </Group>
            <Text size="sm">
              {[item.experience_years !== null && `стаж ${item.experience_years} г.`, item.stack.join(', ')]
                .filter(Boolean)
                .join(' · ')}
            </Text>
            {item.message && (
              <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                «{item.message}»
              </Text>
            )}
            <Text size="sm" c="dimmed">
              Контакты: {[item.contacts.email, item.contacts.phone, item.contacts.telegram].filter(Boolean).join(' · ')}
            </Text>
            {(item.status === 'sent' || item.status === 'viewed') && (
              <Group gap="xs">
                <Button size="xs" disabled={respond.isPending} onClick={() => respond.mutate({ id: item.id, action: 'accept' })}>
                  Принять
                </Button>
                <Button
                  size="xs"
                  variant="default"
                  disabled={respond.isPending}
                  onClick={() => respond.mutate({ id: item.id, action: 'decline' })}
                >
                  Отклонить
                </Button>
              </Group>
            )}
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}

function VacancyForm({ vacancy, onDone }: { vacancy?: EmployerVacancy; onDone: () => void }) {
  const queryClient = useQueryClient()
  const { data: reference } = useReference()
  const form = useForm<VacancyInput>({
    initialValues: vacancy ?? EMPTY,
    validate: {
      title: (value) => (value.trim() ? null : 'Укажите название'),
      description: (value) => (value.trim() ? null : 'Опишите вакансию'),
      specialization: (value) => (value ? null : 'Выберите специализацию'),
      grade: (value) => (value ? null : 'Выберите грейд'),
      salary_from: (value) => (typeof value === 'number' && value > 0 ? null : 'Обязательное поле'),
      salary_to: (value, values) =>
        typeof value !== 'number' || value <= 0
          ? 'Обязательное поле'
          : typeof values.salary_from === 'number' && value < values.salary_from
            ? 'Меньше нижней границы'
            : null,
    },
  })
  const save = useMutation({
    mutationFn: (values: VacancyInput) =>
      api(vacancy ? `/employer/vacancies/${vacancy.id}` : '/employer/vacancies', {
        method: vacancy ? 'PUT' : 'POST',
        body: values,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employer-vacancies'] })
      notifyOk(vacancy ? 'Вакансия сохранена' : 'Вакансия опубликована')
      onDone()
    },
    onError: notifyError,
  })

  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values))}>
      <Stack>
        <TextInput label="Название" placeholder="Например, Python-разработчик" {...form.getInputProps('title')} />
        <Textarea label="Описание" placeholder="Задачи, команда, условия" autosize minRows={4} {...form.getInputProps('description')} />
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Специализация" data={toOptions(reference?.specializations)} {...form.getInputProps('specialization')} />
          <Select label="Грейд" data={toOptions(reference?.grades)} {...form.getInputProps('grade')} />
          <NumberInput label="Зарплата от, ₽" min={0} step={10000} thousandSeparator=" " {...form.getInputProps('salary_from')} />
          <NumberInput label="Зарплата до, ₽" min={0} step={10000} thousandSeparator=" " {...form.getInputProps('salary_to')} />
        </SimpleGrid>
        <TagsInput label="Стек" data={reference?.skills} {...form.getInputProps('stack')} />
        <MultiSelect label="Формат работы" data={toOptions(reference?.work_formats)} {...form.getInputProps('work_formats')} />
        <Group justify="space-between">
          {vacancy ? (
            <Button
              variant="subtle"
              color={vacancy.is_open ? 'red' : 'green'}
              disabled={save.isPending}
              onClick={() => save.mutate({ ...form.values, is_open: !vacancy.is_open })}
            >
              {vacancy.is_open ? 'Закрыть вакансию' : 'Открыть заново'}
            </Button>
          ) : (
            <span />
          )}
          <Button type="submit" loading={save.isPending}>
            {vacancy ? 'Сохранить' : 'Опубликовать'}
          </Button>
        </Group>
      </Stack>
    </form>
  )
}
