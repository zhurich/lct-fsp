import { Button, Group, Paper, SimpleGrid, Stack, Textarea, TextInput, Title } from '@mantine/core'
import { useForm } from '@mantine/form'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { api, type Company } from '../api'
import ConsentSection from '../components/ConsentSection'
import Pending from '../components/Pending'
import { notifyError, notifyOk } from '../notify'

const EMPTY: Company = {
  name: '',
  industry: '',
  description: '',
  website: '',
  contact_person: '',
  contact_email: '',
  contact_phone: '',
}

export default function CompanyPage() {
  const queryClient = useQueryClient()
  const company = useQuery({ queryKey: ['company'], queryFn: () => api<Company>('/employer/company') })
  const form = useForm<Company>({ initialValues: EMPTY })

  useEffect(() => {
    if (company.data) {
      form.setValues(company.data)
      form.resetDirty(company.data)
    }
    // form стабилен между рендерами; зависимость только от загруженных данных
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [company.data])

  const save = useMutation({
    mutationFn: (values: Company) => api<Company>('/employer/company', { method: 'PUT', body: values }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['company'], saved)
      notifyOk('Профиль компании сохранён')
    },
    onError: notifyError,
  })

  if (!company.data) return <Pending queries={[company]} />

  return (
    <Stack maw={860}>
      <form onSubmit={form.onSubmit((values) => save.mutate(values))}>
        <Stack>
          <Title order={2}>Компания</Title>

          <Paper withBorder p="lg">
            <Stack>
              <Title order={4}>Об организации</Title>
              <SimpleGrid cols={{ base: 1, sm: 2 }}>
                <TextInput label="Название" {...form.getInputProps('name')} />
                <TextInput label="Направление деятельности" {...form.getInputProps('industry')} />
              </SimpleGrid>
              <TextInput label="Сайт" {...form.getInputProps('website')} />
              <Textarea label="Описание" autosize minRows={3} {...form.getInputProps('description')} />
            </Stack>
          </Paper>

          <Paper withBorder p="lg">
            <Stack>
              <Title order={4}>Контакты</Title>
              <SimpleGrid cols={{ base: 1, sm: 3 }}>
                <TextInput label="Контактное лицо" {...form.getInputProps('contact_person')} />
                <TextInput label="Почта" {...form.getInputProps('contact_email')} />
                <TextInput label="Телефон" {...form.getInputProps('contact_phone')} />
              </SimpleGrid>
            </Stack>
          </Paper>

          <Group>
            <Button type="submit" loading={save.isPending} disabled={!form.isDirty()}>
              Сохранить
            </Button>
          </Group>
        </Stack>
      </form>
      <ConsentSection deleted="учётная запись, профиль компании, подборки, вакансии, задания и приглашения" />
    </Stack>
  )
}
