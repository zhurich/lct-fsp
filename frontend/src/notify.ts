import { notifications } from '@mantine/notifications'

export const notifyOk = (message: string) => notifications.show({ color: 'green.4', message })

export const notifyError = (error: unknown) =>
  notifications.show({
    color: 'red.5',
    title: 'Не получилось',
    message: error instanceof Error ? error.message : 'Неизвестная ошибка',
  })
