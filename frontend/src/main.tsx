import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/500.css'
import '@fontsource/jetbrains-mono/600.css'
import '@fontsource/jetbrains-mono/700.css'
import '@mantine/core/styles.css'
import '@mantine/notifications/styles.css'
import './styles/tokens.css'
import './styles/fsp.css'

import { MantineProvider } from '@mantine/core'
import { Notifications } from '@mantine/notifications'
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { isSessionLost, signedOut, watchAuth } from './auth'
import { notifyError } from './notify'
import { theme } from './theme'

// Сервер ответил 401 уже вошедшему пользователю: сессия истекла или завершена в другой вкладке.
// Пользователь сбрасывается, и защита маршрутов сама переводит на вход — вместо вечной загрузки.
function onError(error: unknown) {
  if (!isSessionLost(queryClient, error)) return
  signedOut(queryClient)
  notifyError(new Error('Сессия завершена. Войдите снова'))
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
})
watchAuth(queryClient)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MantineProvider theme={theme}>
      <Notifications position="bottom-left" />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
)
