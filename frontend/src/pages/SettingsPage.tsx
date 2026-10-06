import { Alert, Checkbox, List, Paper, Stack, Switch, Text, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, type CandidateProfileFull } from '../api'
import ConsentSection from '../components/ConsentSection'
import FspSection from '../components/FspSection'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'

// Необязательные сведения, которые можно скрыть; ключи совпадают с HIDEABLE_FIELDS на сервере.
const HIDEABLE: { key: string; label: string }[] = [
  { key: 'city', label: 'Город' },
  { key: 'experience', label: 'Стаж' },
  { key: 'work_formats', label: 'Формат работы' },
  { key: 'about', label: 'Раздел «О себе»' },
  { key: 'fsp', label: 'Достижения ФСП' },
]

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const profile = useQuery({
    queryKey: ['candidate-profile'],
    queryFn: () => api<CandidateProfileFull>('/candidate/profile'),
  })
  const save = useMutation({
    mutationFn: (changes: Partial<CandidateProfileFull>) =>
      api<CandidateProfileFull>('/candidate/profile', { method: 'PUT', body: { ...profile.data, ...changes } }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['candidate-profile'], saved)
      notifyOk('Настройки сохранены')
    },
    onError: notifyError,
  })

  if (!profile.data) return <Pending queries={[profile]} />
  const hidden = profile.data.hidden_fields

  return (
    <Stack maw={860}>
      <Title order={2}>Настройки</Title>

      <Paper withBorder p="lg">
        <Stack>
          <Title order={4}>Публикация профиля</Title>
          <Switch
            label="Показывать мой профиль работодателям"
            description="Согласие на публикацию. Пока выключено, вас нет в подборках и вам не приходят приглашения."
            checked={profile.data.is_published}
            disabled={save.isPending}
            onChange={(event) => save.mutate({ is_published: event.currentTarget.checked })}
          />
        </Stack>
      </Paper>

      <Paper withBorder p="lg">
        <Stack>
          <Title order={4}>Что видит работодатель</Title>
          <List size="sm">
            <List.Item>
              <b>Всегда:</b> категория, балл и дата теста, стек — по ним строится подбор. Если тест на
              заявленный грейд не пройден, профиль показывается с пометкой «грейд не подтверждён» и баллом
              этой попытки — ниже кандидатов с категорией.
            </List.Item>
            <List.Item>
              <b>Только после того, как вы примете приглашение:</b> имя, почта, телефон, Telegram.
            </List.Item>
            <List.Item>
              <b>Никогда:</b> ожидаемая зарплата и ответы на задания теста.
            </List.Item>
          </List>
          <Text size="sm" fw={500}>
            Остальное можно скрыть — снимите отметку:
          </Text>
          <Stack gap="xs">
            {HIDEABLE.map(({ key, label }) => (
              <Checkbox
                key={key}
                label={label}
                checked={!hidden.includes(key)}
                disabled={save.isPending}
                onChange={(event) =>
                  save.mutate({
                    hidden_fields: event.currentTarget.checked
                      ? hidden.filter((item) => item !== key)
                      : [...hidden, key],
                  })
                }
              />
            ))}
          </Stack>
          {hidden.includes('fsp') && profile.data.fsp_achievements.length > 0 && (
            <Alert color="yellow">
              Скрытые достижения ФСП не учитываются в подборках: работодатель не видит их и в объяснении выдачи.
            </Alert>
          )}
        </Stack>
      </Paper>

      <FspSection profile={profile.data} />

      <ConsentSection deleted="учётная запись, профиль, результаты тестов и приглашения" />
    </Stack>
  )
}
