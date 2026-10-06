import { Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'

import Logo from './Logo'

/** Фирменные линии-связи: тонкие линии со скруглёнными углами и точками-узлами на концах. */
function BrandLines() {
  return (
    <svg className="fsp-auth__lines" viewBox="0 0 385 313" fill="none" aria-hidden="true">
      <g stroke="#fff" strokeWidth="1">
        <path d="M8 40h150a24 24 0 0 1 24 24v70a24 24 0 0 0 24 24h171" />
        <path d="M8 120h70a24 24 0 0 1 24 24v110a24 24 0 0 0 24 24h251" />
        <path d="M120 8v60a24 24 0 0 0 24 24h130a24 24 0 0 1 24 24v189" />
        <path d="M250 8v200a24 24 0 0 1-24 24H60" />
      </g>
      <g fill="#fff">
        <circle cx="8" cy="40" r="4" />
        <circle cx="377" cy="158" r="4" />
        <circle cx="8" cy="120" r="4" />
        <circle cx="377" cy="278" r="4" />
        <circle cx="120" cy="8" r="4" />
        <circle cx="298" cy="305" r="4" />
        <circle cx="250" cy="8" r="4" />
        <circle cx="60" cy="232" r="4" />
      </g>
    </svg>
  )
}

export default function AuthCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="fsp-auth">
      <aside className="fsp-auth__brand">
        <BrandLines />
        <Logo theme="dark" height={44} />
        <div style={{ position: 'relative', maxWidth: 560 }}>
          <div className="fsp-overline" style={{ color: 'var(--blue-300)', marginBottom: 20 }}>
            Карьерная платформа Федерации
          </div>
          <h1 className="fsp-auth__title">Работодатель сам находит вас</h1>
          <Text size="lg" mt="lg" c="var(--text-inverse-secondary)" maw="48ch">
            Подтвердите уровень тестом, получите категорию — и компании будут приходить с предложением и зарплатной
            вилкой.
          </Text>
        </div>
        <Text size="xs" c="var(--text-inverse-secondary)" style={{ position: 'relative' }}>
          Федерация спортивного программирования России
        </Text>
      </aside>
      <main className="fsp-auth__form">
        <Stack gap="lg" w="100%" maw={420}>
          <div>
            <Text className="fsp-overline" c="dimmed" mb={8} hiddenFrom="md">
              ФСП Карьера
            </Text>
            <Title order={2}>{title}</Title>
          </div>
          {children}
        </Stack>
      </main>
    </div>
  )
}
