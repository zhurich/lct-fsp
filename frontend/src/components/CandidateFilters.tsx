import { Paper, Select, SimpleGrid, Switch, TagsInput } from '@mantine/core'

import { toOptions, useReference } from '../reference'

export type Filters = {
  specialization: string | null
  grade: string | null
  stack: string[]
  work_format: string | null
  fsp_only: boolean
}

export const NO_FILTERS: Filters = { specialization: null, grade: null, stack: [], work_format: null, fsp_only: false }

export function filtersToQuery(filters: Filters): string {
  const params = new URLSearchParams()
  if (filters.specialization) params.set('specialization', filters.specialization)
  if (filters.grade) params.set('grade', filters.grade)
  if (filters.work_format) params.set('work_format', filters.work_format)
  if (filters.fsp_only) params.set('fsp_only', 'true')
  filters.stack.forEach((item) => params.append('stack', item))
  return params.toString()
}

/** Фильтры выдачи; специализация скрывается там, где она задана потребностью. */
export default function CandidateFilters({
  value,
  onChange,
  withSpecialization,
}: {
  value: Filters
  onChange: (filters: Filters) => void
  withSpecialization?: boolean
}) {
  const { data: reference } = useReference()
  return (
    <Paper withBorder p="lg">
      <SimpleGrid cols={{ base: 1, sm: 2, md: withSpecialization ? 4 : 3 }}>
        {withSpecialization && (
          <Select
            label="Специализация"
            placeholder="Любая"
            clearable
            data={toOptions(reference?.specializations)}
            value={value.specialization}
            onChange={(specialization) => onChange({ ...value, specialization })}
          />
        )}
        <Select
          label="Грейд"
          placeholder="Любой"
          clearable
          data={toOptions(reference?.grades)}
          value={value.grade}
          onChange={(grade) => onChange({ ...value, grade })}
        />
        <TagsInput
          label="Обязательный стек"
          placeholder="Технология и Enter"
          data={reference?.skills}
          value={value.stack}
          onChange={(stack) => onChange({ ...value, stack })}
        />
        <Select
          label="Формат работы"
          placeholder="Любой"
          clearable
          data={toOptions(reference?.work_formats)}
          value={value.work_format}
          onChange={(work_format) => onChange({ ...value, work_format })}
        />
      </SimpleGrid>
      <Switch
        mt="md"
        label="Только с подтверждёнными достижениями ФСП"
        checked={value.fsp_only}
        onChange={(event) => onChange({ ...value, fsp_only: event.currentTarget.checked })}
      />
    </Paper>
  )
}
