import { Badge, Button, Group, Paper, Stack, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { api, type Need } from '../api'
import NeedForm from '../components/NeedForm'
import Pending from '../components/Pending'
import { formatDate, formatSalary, useReference } from '../reference'

export default function NeedsPage() {
  const navigate = useNavigate()
  const { specName, gradeName } = useReference()
  const needs = useQuery({ queryKey: ['needs'], queryFn: () => api<Need[]>('/employer/needs') })
  const [creating, setCreating] = useState(false)

  if (!needs.data) return <Pending queries={[needs]} />
  // Первую потребность предлагаем описать сразу, без лишнего клика.
  const showForm = creating || needs.data.length === 0

  return (
    <Stack maw={860}>
      <Group justify="space-between">
        <div>
          <Title order={2}>Подборки</Title>
          <Text c="dimmed" size="sm">
            Опишите, кто вам нужен, — система подберёт категории и кандидатов и объяснит свой выбор.
          </Text>
        </div>
        {!showForm && <Button onClick={() => setCreating(true)}>Новая потребность</Button>}
      </Group>

      {showForm && (
        <Paper withBorder p="lg">
          <Stack>
            <Group justify="space-between">
              <Title order={4}>Новая потребность</Title>
              {needs.data.length > 0 && (
                <Button variant="subtle" color="gray" size="xs" onClick={() => setCreating(false)}>
                  Отмена
                </Button>
              )}
            </Group>
            <NeedForm onSaved={(need) => navigate(`/employer/needs/${need.id}`)} />
          </Stack>
        </Paper>
      )}

      {needs.data.map((need) => (
        <Paper withBorder p="lg" key={need.id} component={Link} to={`/employer/needs/${need.id}`} c="inherit" td="none">
          <Stack gap="xs">
            <Group justify="space-between">
              <Title order={4}>{need.title}</Title>
              <Text size="sm" c="dimmed">
                {formatDate(need.updated_at)}
              </Text>
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
              {need.salary_from && need.salary_to && (
                <Badge variant="default" tt="none">
                  {formatSalary(need.salary_from, need.salary_to)}
                </Badge>
              )}
            </Group>
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}
