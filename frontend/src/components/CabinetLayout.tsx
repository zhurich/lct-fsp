import { AppShell, Badge, Burger, Button, Group, NavLink, Text } from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import { NavLink as RouterLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import type { Role } from '../api'
import { useAuthActions, useMe } from '../auth'
import Logo from './Logo'

// Разделы добавляются сюда по мере реализации.
const NAV: Record<Role, { to: string; label: string }[]> = {
  candidate: [
    { to: '/candidate/assessment', label: 'Тест и категория' },
    { to: '/candidate/invitations', label: 'Приглашения' },
    { to: '/candidate/vacancies', label: 'Вакансии' },
    { to: '/candidate/challenges', label: 'Задания' },
    { to: '/candidate/profile', label: 'Профиль' },
    { to: '/candidate/settings', label: 'Настройки' },
  ],
  employer: [
    { to: '/employer/needs', label: 'Подборки' },
    { to: '/employer/candidates', label: 'Банк кандидатов' },
    { to: '/employer/invitations', label: 'Приглашения' },
    { to: '/employer/vacancies', label: 'Вакансии' },
    { to: '/employer/challenges', label: 'Задания' },
    { to: '/employer/company', label: 'Компания' },
  ],
}

const ROLE_LABEL: Record<Role, string> = { candidate: 'Кандидат', employer: 'Работодатель' }

export default function CabinetLayout() {
  const { data: user } = useMe()
  const { logout } = useAuthActions()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [opened, { toggle, close }] = useDisclosure()

  if (!user) return null

  return (
    <AppShell
      header={{ height: 72 }}
      navbar={{ width: 248, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="lg"
    >
      <AppShell.Header>
        <Group h="100%" px="lg" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Меню" />
            <Logo height={32} />
            <Text fw={500} size="lg" visibleFrom="xs" style={{ letterSpacing: 'var(--ls-heading)' }}>
              Карьера
            </Text>
            <Badge variant="light">{ROLE_LABEL[user.role]}</Badge>
          </Group>
          <Group gap="sm" wrap="nowrap">
            <Text size="sm" c="dimmed" visibleFrom="sm">
              {user.email}
            </Text>
            <Button
              variant="default"
              size="xs"
              onClick={async () => {
                await logout()
                navigate('/login')
              }}
            >
              Выйти
            </Button>
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="sm" className="fsp-nav">
        {NAV[user.role].map((item) => (
          <NavLink
            key={item.to}
            component={RouterLink}
            to={item.to}
            label={item.label}
            active={pathname.startsWith(item.to)}
            onClick={close}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  )
}
