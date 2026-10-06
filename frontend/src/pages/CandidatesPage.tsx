import { Alert, Stack, Text, Title } from '@mantine/core'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { api, type CandidateCard } from '../api'
import CandidateFilters, { type Filters, filtersToQuery, NO_FILTERS } from '../components/CandidateFilters'
import CandidateList from '../components/CandidateList'
import Pending from '../components/Pending'

export default function CandidatesPage() {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS)
  const candidates = useQuery({
    queryKey: ['candidates', filters],
    queryFn: () => api<CandidateCard[]>(`/employer/candidates?${filtersToQuery(filters)}`),
    // При уточнении фильтров прежняя выдача остаётся на экране до прихода новой.
    placeholderData: keepPreviousData,
  })
  const verified = candidates.data?.filter((card) => card.verified) ?? []
  const unverified = candidates.data?.filter((card) => !card.verified) ?? []

  return (
    <Stack maw={960}>
      <div>
        <Title order={2}>Банк кандидатов</Title>
        <Text c="dimmed" size="sm">
          Вся база: сначала кандидаты с подтверждённой категорией, затем те, чей грейд пока не подтверждён. Чтобы получить подборку под конкретную задачу, опишите
          потребность в разделе «Подборки».
        </Text>
      </div>
      <CandidateFilters value={filters} onChange={setFilters} withSpecialization />
      {!candidates.data ? (
        <Pending queries={[candidates]} />
      ) : candidates.data.length === 0 ? (
        <Alert color="gray" title="Никого не нашлось">
          В банке нет кандидатов с такими параметрами. Попробуйте ослабить фильтры.
        </Alert>
      ) : (
        <Text size="sm" c="dimmed">
          С подтверждённой категорией: {verified.length}. Сортировка — по силе подтверждённого профиля. Имя и контакты
          откроются, когда кандидат примет приглашение.
        </Text>
      )}
      <CandidateList cards={verified} />
      {unverified.length > 0 && (
        <>
          <div>
            <Title order={4}>Грейд не подтверждён — {unverified.length}</Title>
            <Text size="sm" c="dimmed">
              Кандидаты заявили грейд, но тест на него не прошли. Показываются после подтверждённых и без
              оценки; пригласить их можно на общих основаниях.
            </Text>
          </div>
          <CandidateList cards={unverified} />
        </>
      )}
    </Stack>
  )
}
