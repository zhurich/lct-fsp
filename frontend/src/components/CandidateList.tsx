import {
  Badge,
  Button,
  Group,
  List,
  Modal,
  NumberInput,
  Paper,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { memo, useState } from 'react'

import { api, type CandidateCard, type Company } from '../api'
import { notifyError, notifyOk } from '../notify'
import { FSP_LEVEL, formatDate, INVITATION_STATUS, NOTE_BELOW, SALARY_NOTE, useReference } from '../reference'
import Pending from './Pending'

export type InviteDefaults = { title?: string; salary_from?: number | null; salary_to?: number | null }

// Карточки показываются порциями: вся база на одной странице — десятки тысяч узлов DOM.
const PAGE_SIZE = 20

// Знак довода в объяснении выдачи. Красный не используется: на экране он один, и это не оценка кандидата.
const REASON_MARK = {
  plus: { sign: '+', color: 'green' },
  minus: { sign: '−', color: 'dark' },
  info: { sign: '·', color: 'dimmed' },
} as const

/** Список карточек кандидатов с приглашением; общий для подборки и банка. */
export default function CandidateList({ cards, inviteDefaults }: { cards: CandidateCard[]; inviteDefaults?: InviteDefaults }) {
  const { specName, gradeName } = useReference()
  const [invited, setInvited] = useState<CandidateCard | null>(null)
  const [shown, setShown] = useState(PAGE_SIZE)
  return (
    <>
      {cards.slice(0, shown).map((card) => (
        <CardView key={card.candidate_id} card={card} onInvite={setInvited} />
      ))}
      {cards.length > shown && (
        <Button variant="default" onClick={() => setShown(shown + PAGE_SIZE)}>
          Показать ещё {Math.min(PAGE_SIZE, cards.length - shown)} из {cards.length - shown}
        </Button>
      )}
      <Modal
        opened={invited !== null}
        onClose={() => setInvited(null)}
        title={invited && `Приглашение: ${specName(invited.specialization)} · ${gradeName(invited.grade)}`}
        size="lg"
      >
        {invited && <InviteForm candidate={invited} defaults={inviteDefaults} onDone={() => setInvited(null)} />}
      </Modal>
    </>
  )
}

// memo: открытие и закрытие приглашения меняет состояние списка, карточки при этом перерисовывать незачем.
const CardView = memo(function CardView({ card, onInvite }: { card: CandidateCard; onInvite: (card: CandidateCard) => void }) {
  const { specName, gradeName, formatName } = useReference()
  const prizes = card.fsp_achievements.filter((item) => item.place)
  return (
    <Paper withBorder p="lg">
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start">
          <div>
            <Group gap="xs">
              <Title order={4}>
                {specName(card.specialization)} · {gradeName(card.grade)}
              </Title>
              {!card.verified && (
                <Badge color="yellow" variant="light">
                  Грейд не подтверждён
                </Badge>
              )}
              {card.fsp_achievements.length > 0 && (
                <Badge color="dark">
                  ФСП: {prizes.length > 0 ? `призовых мест — ${prizes.length}` : 'участник соревнований'}
                </Badge>
              )}
            </Group>
            <Text size="sm" c="dimmed">
              {[
                `Кандидат №${card.candidate_id}`,
                card.experience_years !== null && `стаж ${card.experience_years} г.`,
                card.city,
                card.work_formats.map(formatName).join(', '),
                `${card.verified ? 'тест от' : 'тест не пройден'} ${formatDate(card.category_assigned_at)}`,
              ]
                .filter(Boolean)
                .join(' · ')}
            </Text>
          </div>
          <Stack gap={6} align="flex-end">
            {card.score !== null && (
              <Badge size="xl" variant="light" color={card.score >= 70 ? 'green' : card.score >= 50 ? 'blue' : 'gray'}>
                Оценка {Math.round(card.score)}
              </Badge>
            )}
            {card.invitation_status && card.invitation_status !== 'declined' ? (
              <Badge color={INVITATION_STATUS[card.invitation_status].color} variant="light">
                Приглашение: {INVITATION_STATUS[card.invitation_status].label.toLowerCase()}
              </Badge>
            ) : (
              <Button onClick={() => onInvite(card)}>Пригласить</Button>
            )}
          </Stack>
        </Group>
        {card.stack.length > 0 && (
          <Group gap={6}>
            {card.stack.map((item) => (
              <Badge
                key={item}
                tt="none"
                variant={card.matched_stack.some((name) => name.toLowerCase() === item.toLowerCase()) ? 'filled' : 'default'}
              >
                {item}
              </Badge>
            ))}
          </Group>
        )}
        {card.about && <Text lineClamp={3}>{card.about}</Text>}
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
          <div>
            <Text size="sm" fw={500} mb={4}>
              {card.verified ? 'Почему в подборке' : 'Статус и соответствие запросу'}
            </Text>
            <Stack gap={4}>
              {card.reasons.map((reason) => (
                <Group key={reason.text} gap={8} wrap="nowrap" align="flex-start">
                  <Text size="sm" fw={700} w={10} ta="center" c={REASON_MARK[reason.kind].color}>
                    {REASON_MARK[reason.kind].sign}
                  </Text>
                  <Text size="sm">{reason.text}</Text>
                </Group>
              ))}
            </Stack>
          </div>
          {card.breakdown.length > 0 && (
          <div>
            <Text size="sm" fw={500} mb={4}>
              Из чего сложилась оценка
            </Text>
            <Stack gap={4}>
              {card.breakdown.map((part) => (
                <Group key={part.key} gap="xs" wrap="nowrap">
                  <Text size="xs" w={110}>
                    {part.label}
                  </Text>
                  <Progress value={part.value * 100} style={{ flex: 1 }} aria-label={part.label} />
                  <Text size="xs" w={28} ta="right">
                    {Math.round(part.value * 100)}
                  </Text>
                </Group>
              ))}
            </Stack>
          </div>
          )}
        </SimpleGrid>
        {card.fsp_achievements.length > 0 && (
          <div>
            <Text size="sm" fw={500} mb={4}>
              Подтверждённые достижения ФСП{card.fsp_rank && ` · ${card.fsp_rank.toLowerCase()}`}
            </Text>
            <List size="sm">
              {card.fsp_achievements.slice(0, 4).map((item, index) => (
                <List.Item key={index}>
                  {item.place ? `${item.place} место` : 'Участие'} · {item.event} ({FSP_LEVEL[item.level] ?? item.level}
                  ), {item.discipline.toLowerCase()}, {new Date(item.date).getFullYear()}
                  {item.team && ', командный результат'}
                </List.Item>
              ))}
            </List>
            {card.fsp_achievements.length > 4 && (
              <Text size="xs" c="dimmed">
                и ещё {card.fsp_achievements.length - 4}
              </Text>
            )}
          </div>
        )}
      </Stack>
    </Paper>
  )
})

type InviteProps = { candidate: CandidateCard; defaults?: InviteDefaults; onDone: () => void }

function InviteForm(props: InviteProps) {
  const company = useQuery({ queryKey: ['company'], queryFn: () => api<Company>('/employer/company') })
  if (!company.data) return <Pending queries={[company]} />
  // Способ связи по умолчанию — контакты из профиля компании.
  const { contact_person, contact_email, contact_phone } = company.data
  const contact = [contact_person, contact_email, contact_phone].filter(Boolean).join(', ')
  return <InviteFields {...props} defaultContact={contact} />
}

function InviteFields({ candidate, defaults, onDone, defaultContact }: InviteProps & { defaultContact: string }) {
  const queryClient = useQueryClient()
  const form = useForm({
    initialValues: {
      title: defaults?.title ?? '',
      message: '',
      salary_from: (defaults?.salary_from ?? '') as number | string,
      salary_to: (defaults?.salary_to ?? '') as number | string,
      contact: defaultContact,
    },
    validate: {
      title: (value) => (value.trim() ? null : 'Укажите должность'),
      message: (value) => (value.trim() ? null : 'Опишите предложение'),
      salary_from: (value) => (typeof value === 'number' && value > 0 ? null : 'Укажите нижнюю границу'),
      salary_to: (value, values) =>
        typeof value !== 'number' || value <= 0
          ? 'Укажите верхнюю границу'
          : typeof values.salary_from === 'number' && value < values.salary_from
            ? 'Меньше нижней границы'
            : null,
      contact: (value) => (value.trim() ? null : 'Укажите, как с вами связаться'),
    },
  })
  const send = useMutation({
    mutationFn: (values: typeof form.values) =>
      api('/employer/invitations', { method: 'POST', body: { ...values, candidate_id: candidate.candidate_id } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['candidates'] })
      queryClient.invalidateQueries({ queryKey: ['matches'] })
      queryClient.invalidateQueries({ queryKey: ['employer-invitations'] })
      notifyOk('Приглашение отправлено')
      onDone()
    },
    onError: notifyError,
  })

  return (
    <form onSubmit={form.onSubmit((values) => send.mutate(values))}>
      <Stack>
        <Text size="sm" c="dimmed">
          Кандидат увидит название вашей компании, предложение и зарплатную вилку до начала общения.
        </Text>
        <TextInput label="Должность" placeholder="Например, Python-разработчик" {...form.getInputProps('title')} />
        <Textarea
          label="Описание предложения"
          placeholder="Чем занимается команда, задачи, условия"
          autosize
          minRows={4}
          {...form.getInputProps('message')}
        />
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <NumberInput
            label="Зарплата от, ₽"
            description={SALARY_NOTE}
            inputWrapperOrder={NOTE_BELOW}
            min={0}
            step={10000}
            thousandSeparator=" "
            {...form.getInputProps('salary_from')}
          />
          <NumberInput
            label="Зарплата до, ₽"
            description={SALARY_NOTE}
            inputWrapperOrder={NOTE_BELOW}
            min={0}
            step={10000}
            thousandSeparator=" "
            {...form.getInputProps('salary_to')}
          />
        </SimpleGrid>
        <TextInput
          label="Способ связи"
          description="Почта, телефон или мессенджер, по которому кандидат сможет ответить"
          {...form.getInputProps('contact')}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onDone}>
            Отмена
          </Button>
          <Button type="submit" loading={send.isPending}>
            Отправить приглашение
          </Button>
        </Group>
      </Stack>
    </form>
  )
}
