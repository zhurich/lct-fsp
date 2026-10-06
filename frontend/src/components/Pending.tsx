import { Alert, Button, Group, Loader } from '@mantine/core'

type PendingQuery = { error: unknown; isFetching: boolean; refetch: () => unknown }

/** Заглушка на месте ещё не загруженных данных: индикатор либо ошибка с повтором, а не вечная загрузка. */
export default function Pending({ queries }: { queries: PendingQuery[] }) {
  const failed = queries.filter((query) => query.error)
  if (failed.length === 0) return <Loader />
  const [{ error }] = failed
  return (
    <Alert color="gray" title="Не удалось загрузить данные" maw={560}>
      {error instanceof Error ? error.message : 'Неизвестная ошибка'}
      <Group mt="sm">
        <Button
          size="xs"
          variant="default"
          loading={failed.some((query) => query.isFetching)}
          onClick={() => failed.forEach((query) => query.refetch())}
        >
          Повторить
        </Button>
      </Group>
    </Alert>
  )
}
