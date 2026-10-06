import { Alert, Button, Loader, Stack } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'

import { api } from '../api'
import AuthCard from '../components/AuthCard'

export default function VerifyPage() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''
  const { isPending, error } = useQuery({
    queryKey: ['verify', token],
    queryFn: () => api('/auth/verify', { method: 'POST', body: { token } }),
  })

  return (
    <AuthCard title="Подтверждение почты">
      {isPending ? (
        <Loader />
      ) : (
        <Stack>
          {error ? (
            <Alert color="red">{error.message}</Alert>
          ) : (
            <Alert color="green">Почта подтверждена. Теперь можно войти.</Alert>
          )}
          <Button component={Link} to="/login">
            Перейти ко входу
          </Button>
        </Stack>
      )}
    </AuthCard>
  )
}
