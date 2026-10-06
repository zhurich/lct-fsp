import {
  Alert,
  Button,
  FileButton,
  Group,
  List,
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
import { useEffect, useState } from 'react'

import {
  api,
  apiUpload,
  type CandidateProfile,
  type CandidateProfileFull,
  type ParsedResume,
  type Reference,
} from '../api'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'
import { NOTE_BELOW, SALARY_NOTE } from '../reference'

const EMPTY: CandidateProfile = {
  full_name: '',
  phone: '',
  telegram: '',
  city: '',
  about: '',
  specialization: null,
  stack: [],
  roles: [],
  soft_skills: [],
  experience_years: 0,
  work_formats: [],
  salary_expectation: null,
  is_published: false,
  hidden_fields: [],
}

const options = (items: { code: string; name: string }[] = []) =>
  items.map((item) => ({ value: item.code, label: item.name }))

export default function CandidateProfilePage() {
  const queryClient = useQueryClient()
  const reference = useQuery({ queryKey: ['reference'], queryFn: () => api<Reference>('/reference') })
  const profile = useQuery({
    queryKey: ['candidate-profile'],
    queryFn: () => api<CandidateProfileFull>('/candidate/profile'),
  })
  const form = useForm<CandidateProfile>({
    initialValues: EMPTY,
    validate: {
      // Очищенное числовое поле даёт пустую строку — сервер её не примет.
      experience_years: (value) => (typeof value === 'number' ? null : 'Укажите стаж числом; если опыта нет — 0'),
    },
  })

  useEffect(() => {
    if (profile.data) {
      form.setValues(profile.data)
      form.resetDirty(profile.data)
    }
    // form стабилен между рендерами; зависимость только от загруженных данных
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile.data])

  const save = useMutation({
    mutationFn: (values: CandidateProfile) =>
      api<CandidateProfileFull>('/candidate/profile', { method: 'PUT', body: values }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['candidate-profile'], saved)
      notifyOk('Профиль сохранён')
    },
    onError: notifyError,
  })

  const [resumeNotes, setResumeNotes] = useState<string[] | null>(null)
  const resume = useMutation({
    mutationFn: (file: File) => apiUpload<ParsedResume>('/candidate/profile/resume', file),
    onSuccess: ({ notes, claimed_grade, ...fields }) => {
      // Подставляется только распознанное: заполненное вручную пустыми значениями не затирается.
      const filled = Object.fromEntries(
        Object.entries(fields).filter(([, value]) => (Array.isArray(value) ? value.length > 0 : Boolean(value))),
      )
      form.setValues(filled)
      setResumeNotes(notes)
      // Заявленный в резюме грейд пригодится в опросе перед тестом.
      queryClient.setQueryData(['resume-grade'], claimed_grade)
    },
    onError: notifyError,
  })

  if (!profile.data) return <Pending queries={[profile]} />

  return (
    <Stack maw={860}>
      <form onSubmit={form.onSubmit((values) => save.mutate(values))}>
        <Stack>
          <Group justify="space-between">
            <Title order={2}>Профиль</Title>
            <Button component="a" href="/api/candidate/profile/pdf" variant="default" size="xs">
              Скачать PDF-профиль
            </Button>
          </Group>

          <Paper withBorder p="lg">
            <Stack gap="sm">
              <Title order={4}>Заполнить из резюме</Title>
              <Text size="sm" c="dimmed">
                Загрузите резюме в PDF — мы распознаем контакты, стек, стаж и роли и подставим их в форму. Файл не
                сохраняется; проверьте поля и нажмите «Сохранить».
              </Text>
              <Group>
                <FileButton onChange={(file) => file && resume.mutate(file)} accept="application/pdf">
                  {(props) => (
                    <Button {...props} variant="light" loading={resume.isPending}>
                      Выбрать PDF
                    </Button>
                  )}
                </FileButton>
              </Group>
              {resumeNotes && (
                <Alert color="blue" title="Распознано — проверьте поля ниже">
                  <List size="sm">
                    {resumeNotes.map((note) => (
                      <List.Item key={note}>{note}</List.Item>
                    ))}
                  </List>
                </Alert>
              )}
            </Stack>
          </Paper>

          <Paper withBorder p="lg">
            <Stack>
              <Title order={4}>Контакты</Title>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <TextInput label="ФИО" {...form.getInputProps('full_name')} />
                <TextInput label="Город" {...form.getInputProps('city')} />
                <TextInput label="Телефон" {...form.getInputProps('phone')} />
                <TextInput label="Telegram" {...form.getInputProps('telegram')} />
              </SimpleGrid>
            </Stack>
          </Paper>

          <Paper withBorder p="lg">
            <Stack>
              <Title order={4}>Опыт и навыки</Title>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <Select
                  label="Специализация"
                  placeholder="Выберите направление"
                  data={options(reference.data?.specializations)}
                  clearable
                  {...form.getInputProps('specialization')}
                />
                <NumberInput
                  label="Стаж, лет"
                  min={0}
                  max={60}
                  step={0.5}
                  {...form.getInputProps('experience_years')}
                />
              </SimpleGrid>
              <TagsInput
                label="Стек"
                description="Введите технологию и нажмите Enter"
                data={reference.data?.skills}
                {...form.getInputProps('stack')}
              />
              <TagsInput label="Роли в команде" {...form.getInputProps('roles')} />
              <TagsInput label="Софт-скиллы" {...form.getInputProps('soft_skills')} />
              <Textarea
                label="О себе"
                description="Почту, телефон и ссылки отсюда работодатель не увидит: контакты открываются только после того, как вы примете приглашение"
                autosize
                minRows={3}
                {...form.getInputProps('about')}
              />
            </Stack>
          </Paper>

          <Paper withBorder p="lg">
            <Stack>
              <Title order={4}>Пожелания к работе</Title>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <MultiSelect
                  label="Формат работы"
                  data={options(reference.data?.work_formats)}
                  {...form.getInputProps('work_formats')}
                />
                <NumberInput
                  label={`Ожидаемая зарплата, ₽ (${SALARY_NOTE})`}
                  description="Работодателю не показывается"
                  inputWrapperOrder={NOTE_BELOW}
                  min={0}
                  step={10000}
                  thousandSeparator=" "
                  {...form.getInputProps('salary_expectation')}
                  value={form.values.salary_expectation ?? ''}
                  onChange={(value) =>
                    form.setFieldValue('salary_expectation', typeof value === 'number' ? value : null)
                  }
                />
              </SimpleGrid>
            </Stack>
          </Paper>

          <Group>
            <Button type="submit" loading={save.isPending} disabled={!form.isDirty()}>
              Сохранить
            </Button>
          </Group>
        </Stack>
      </form>
    </Stack>
  )
}
