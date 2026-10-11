import { Alert, Anchor, Badge, Button, Group, Modal, Paper, Stack, Text, Title } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError, api, type Matches } from '../api'
import CandidateFilters, { type Filters, filtersToQuery, NO_FILTERS } from '../components/CandidateFilters'
import CandidateList from '../components/CandidateList'
import NeedForm from '../components/NeedForm'
import Pending from '../components/Pending'
import { notifyError } from '../notify'
import { formatSalary, useReference } from '../reference'

export default function NeedPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { specName, gradeName, formatName } = useReference()
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const [editing, edit] = useDisclosure()
  const matches = useQuery({
    queryKey: ['matches', id, filters],
    queryFn: () => api<Matches>(`/employer/needs/${id}/matches?${filtersToQuery(filters)}`),
    // Уточнение фильтров не сбрасывает уже показанную подборку.
    placeholderData: keepPreviousData,
  })
  const remove = useMutation({
    mutationFn: () => api(`/employer/needs/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['needs'] })
      navigate('/employer/needs')
    },
    onError: notifyError,
  })

  if (matches.error instanceof ApiError && matches.error.status === 404) {
    return (
      <Alert color="gray" title="Подборка не найдена">
        <Anchor component={Link} to="/employer/needs">
          К списку подборок
        </Anchor>
      </Alert>
    )
  }
  if (!matches.data) return <Pending queries={[matches]} />
  const { need, categories, total, candidates, unverified } = matches.data
  // Приглашение из подборки сразу заполнено по её потребности.
  const inviteDefaults = {
    title: need.title,
    message: need.text,
    salary_from: need.salary_from,
    salary_to: need.salary_to,
  }
  const filtered = candidates.length !== total

  return (
    <Stack maw={960}>
      <Anchor component={Link} to="/employer/needs" size="sm">
        ← Все подборки
      </Anchor>
      <Paper withBorder p="lg">
        <Stack gap="sm">
          <Group justify="space-between" align="flex-start">
            <Title order={2}>{need.title}</Title>
            <Group gap="xs">
              <Button variant="default" size="xs" onClick={edit.open}>
                Изменить
              </Button>
              <Button
                variant="subtle"
                color="red"
                size="xs"
                loading={remove.isPending}
                onClick={() => window.confirm('Удалить подборку? Отправленные приглашения сохранятся.') && remove.mutate()}
              >
                Удалить
              </Button>
            </Group>
          </Group>
          <Group gap={6}>
            <Badge variant="light">
              {specName(need.specialization)} · {gradeName(need.grade)}
            </Badge>
            {need.stack.map((item) => (
              <Badge key={item} variant="default" tt="none">
                {item}
              </Badge>
            ))}
            {need.work_formats.map((code) => (
              <Badge key={code} variant="default" tt="none">
                {formatName(code)}
              </Badge>
            ))}
            {need.salary_from && need.salary_to && (
              <Badge variant="default" tt="none">
                {formatSalary(need.salary_from, need.salary_to)}
              </Badge>
            )}
          </Group>
          {need.text && (
            <Text size="sm" c="dimmed" lineClamp={3} style={{ whiteSpace: 'pre-wrap' }}>
              {need.text}
            </Text>
          )}
        </Stack>
      </Paper>

      <div>
        <Title order={4} mb="xs">
          Рекомендованные категории
        </Title>
        <Group gap="sm">
          {categories.map((category) => {
            const active = filters.grade === category.grade
            return (
              <Button
                key={category.grade}
                variant={active ? 'filled' : 'default'}
                disabled={category.count === 0 && !active}
                onClick={() => setFilters({ ...filters, grade: active ? null : category.grade })}
              >
                {specName(category.specialization)} · {gradeName(category.grade)} — {category.count}
                {category.exact ? ' · точное соответствие' : ' · смежный грейд'}
              </Button>
            )
          })}
        </Group>
      </div>

      <CandidateFilters value={filters} onChange={setFilters} />

      {total === 0 ? (
        <Alert color="gray" title="Подходящих кандидатов пока нет">
          В этой и смежных категориях ещё никто не подтвердил грейд тестом. Подборка обновляется сама: загляните
          позже или измените потребность.
        </Alert>
      ) : candidates.length === 0 ? (
        <Alert color="gray" title="Фильтры отсекли всех кандидатов">
          В подборке {total}, но уточняющим фильтрам никто не соответствует.{' '}
          <Anchor component="button" onClick={() => setFilters(NO_FILTERS)}>
            Сбросить фильтры
          </Anchor>
        </Alert>
      ) : (
        <Text size="sm" c="dimmed">
          {filtered ? `Показано ${candidates.length} из ${total}` : `В подборке: ${total}`}. Порядок — по оценке:
          сначала соответствие потребности, при равном — сила подтверждённого профиля.{' '}
          {filtered && (
            <Anchor component="button" size="sm" onClick={() => setFilters(NO_FILTERS)}>
              Сбросить фильтры
            </Anchor>
          )}
        </Text>
      )}
      <CandidateList cards={candidates} inviteDefaults={inviteDefaults} />

      {unverified.length > 0 && (
        <>
          <div>
            <Title order={4}>Грейд не подтверждён — {unverified.length}</Title>
            <Text size="sm" c="dimmed">
              Эти кандидаты заявили запрошенный или смежный грейд, но тест на него не прошли. Оценки у них
              нет, поэтому они всегда ниже подборки; порядок — по совпадению стека и баллу теста. Пригласить
              их можно на общих основаниях.
            </Text>
          </div>
          <CandidateList cards={unverified} inviteDefaults={inviteDefaults} />
        </>
      )}

      <Modal opened={editing} onClose={edit.close} title="Изменить потребность" size="lg">
        <NeedForm need={need} onSaved={edit.close} />
      </Modal>
    </Stack>
  )
}
