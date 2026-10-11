import {
  Alert,
  Button,
  Group,
  List,
  MultiSelect,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  TagsInput,
  Textarea,
  TextInput,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type Need, type NeedInput, type ParsedNeed } from '../api'
import { notifyError } from '../notify'
import { toOptions, useReference } from '../reference'

const EMPTY: NeedInput = {
  title: '',
  text: '',
  specialization: null,
  grade: null,
  stack: [],
  work_formats: [],
  salary_from: null,
  salary_to: null,
}

const numberOrNull = (value: number | string) => (typeof value === 'number' ? value : null)

/** Создание и правка потребности: свободный текст разбирается в поля, которые можно поправить вручную. */
export default function NeedForm({ need, onSaved }: { need?: Need; onSaved: (need: Need) => void }) {
  const queryClient = useQueryClient()
  const { data: reference, specName, gradeName } = useReference()
  const [notes, setNotes] = useState<string[] | null>(null)
  const form = useForm<NeedInput>({
    initialValues: need ?? EMPTY,
    validate: {
      specialization: (value) => (value ? null : 'Выберите специализацию'),
      grade: (value) => (value ? null : 'Выберите грейд'),
      salary_to: (value, values) =>
        value && values.salary_from && value < values.salary_from ? 'Меньше нижней границы' : null,
    },
  })

  const parse = useMutation({
    mutationFn: () => api<ParsedNeed>('/employer/needs/parse', { method: 'POST', body: { text: form.values.text } }),
    onSuccess: ({ notes: parsedNotes, ...fields }) => {
      // Разбор заполняет только то, что распознал: введённое вручную не затирается пустым.
      form.setValues({
        specialization: fields.specialization ?? form.values.specialization,
        grade: fields.grade ?? form.values.grade,
        stack: fields.stack.length ? fields.stack : form.values.stack,
        work_formats: fields.work_formats.length ? fields.work_formats : form.values.work_formats,
        salary_from: fields.salary_from ?? form.values.salary_from,
        salary_to: fields.salary_to ?? form.values.salary_to,
      })
      setNotes(parsedNotes)
    },
    onError: notifyError,
  })

  const save = useMutation({
    mutationFn: (values: NeedInput) => {
      // Название по умолчанию собирается из категории.
      const title = values.title.trim() || `${specName(values.specialization)} · ${gradeName(values.grade)}`
      return api<Need>(need ? `/employer/needs/${need.id}` : '/employer/needs', {
        method: need ? 'PUT' : 'POST',
        body: { ...values, title },
      })
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: ['needs'] })
      queryClient.invalidateQueries({ queryKey: ['matches'] })
      onSaved(saved)
    },
    onError: notifyError,
  })

  return (
    <form onSubmit={form.onSubmit((values) => save.mutate(values))}>
      <Stack>
        <Textarea
          label="Кого вы ищете"
          description="Опишите своими словами: чем занимается команда, какой специалист нужен, стек, уровень, условия"
          placeholder="Например: в команду платежей нужен middle бэкенд-разработчик, Python, FastAPI, PostgreSQL, Kafka. Удалённо, от 200 до 280 тыс."
          autosize
          minRows={4}
          {...form.getInputProps('text')}
        />
        <Group>
          <Button
            variant="light"
            loading={parse.isPending}
            disabled={!form.values.text.trim()}
            onClick={() => parse.mutate()}
          >
            Разобрать описание
          </Button>
        </Group>
        {notes && (
          <Alert color="blue" title="Что удалось распознать — проверьте и поправьте поля ниже">
            <List size="sm">
              {notes.map((note) => (
                <List.Item key={note}>{note}</List.Item>
              ))}
            </List>
          </Alert>
        )}
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select
            label="Специализация"
            placeholder="Выберите направление"
            data={toOptions(reference?.specializations)}
            {...form.getInputProps('specialization')}
          />
          <Select
            label="Грейд"
            placeholder="Выберите уровень"
            description="Кандидаты смежных грейдов тоже попадут в подборку, но ниже"
            data={toOptions(reference?.grades)}
            {...form.getInputProps('grade')}
          />
        </SimpleGrid>
        <TagsInput
          label="Требуемый стек"
          description="Введите технологию и нажмите Enter"
          data={reference?.skills}
          {...form.getInputProps('stack')}
        />
        <SimpleGrid cols={{ base: 1, sm: 3 }}>
          <MultiSelect
            label="Формат работы"
            placeholder="Любой"
            data={toOptions(reference?.work_formats)}
            {...form.getInputProps('work_formats')}
          />
          <NumberInput
            label="Зарплата от, ₽"
            min={0}
            step={10000}
            thousandSeparator=" "
            value={form.values.salary_from ?? ''}
            onChange={(value) => form.setFieldValue('salary_from', numberOrNull(value))}
          />
          <NumberInput
            label="Зарплата до, ₽"
            min={0}
            step={10000}
            thousandSeparator=" "
            error={form.errors.salary_to}
            value={form.values.salary_to ?? ''}
            onChange={(value) => form.setFieldValue('salary_to', numberOrNull(value))}
          />
        </SimpleGrid>
        <TextInput
          label="Название подборки"
          placeholder="По умолчанию — специализация и грейд"
          {...form.getInputProps('title')}
        />
        <Group>
          <Button type="submit" loading={save.isPending}>
            {need ? 'Сохранить' : 'Сохранить и показать подборку'}
          </Button>
        </Group>
      </Stack>
    </form>
  )
}
