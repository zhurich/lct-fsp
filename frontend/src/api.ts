export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
  }
}

type Options = { method?: 'GET' | 'POST' | 'PUT' | 'DELETE'; body?: unknown }

export async function api<T>(path: string, { method = 'GET', body }: Options = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  return response.status === 204 ? (undefined as T) : response.json()
}

/** Отправка одного файла формой; имя поля — file. */
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const body = new FormData()
  body.append('file', file)
  const response = await fetch(`/api${path}`, { method: 'POST', credentials: 'same-origin', body })
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  return response.json()
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const { detail } = await response.json()
    if (typeof detail === 'string') return detail
    // Ошибки валидации FastAPI приходят списком.
    if (Array.isArray(detail)) return detail.map((item) => item.msg).join('; ')
  } catch {
    // тело не JSON — ниже вернём общий текст
  }
  return `Ошибка сервера (${response.status})`
}

export type Role = 'candidate' | 'employer'
export type User = { id: number; email: string; role: Role; consent_at: string }
export type RefItem = { code: string; name: string; description?: string | null }
export type Reference = {
  specializations: RefItem[]
  grades: RefItem[]
  work_formats: RefItem[]
  /** Словарь технологий для подсказок при вводе стека. */
  skills: string[]
}

export type CandidateProfile = {
  full_name: string
  phone: string
  telegram: string
  city: string
  about: string
  specialization: string | null
  stack: string[]
  roles: string[]
  soft_skills: string[]
  experience_years: number
  work_formats: string[]
  salary_expectation: number | null
  is_published: boolean
  /** Необязательные сведения, скрытые от работодателей. */
  hidden_fields: string[]
}

/** Черновик профиля, распознанный из PDF-резюме. */
export type ParsedResume = {
  full_name: string
  phone: string
  telegram: string
  city: string
  about: string
  specialization: string | null
  claimed_grade: string | null
  stack: string[]
  roles: string[]
  soft_skills: string[]
  experience_years: number | null
  work_formats: string[]
  notes: string[]
}

export type FspAchievement = {
  event: string
  discipline: string
  level: string
  /** null — участие без призового места. */
  place: number | null
  date: string
  /** Командный результат. */
  team?: boolean
}
/** Профиль с полями, которые меняются не формой, а привязкой ФСП ID. */
export type CandidateProfileFull = CandidateProfile & {
  fsp_id: string | null
  fsp_achievements: FspAchievement[]
  /** Спортивный разряд из реестра ФСП. */
  fsp_rank: string | null
  fsp_synced_at: string | null
}

export type Company = {
  name: string
  industry: string
  description: string
  website: string
  contact_person: string
  contact_email: string
  contact_phone: string
}

export type AttemptStatus = 'in_progress' | 'passed' | 'failed'
export type Question = { text: string; code: string | null; options: string[] }
export type Attempt = {
  id: number
  specialization: string
  grade: string
  status: AttemptStatus
  /** Балл теста 0…1 по шкале IRT. */
  score: number | null
  /** Грейд, которому соответствует результат завершённого теста. */
  estimated_grade: string | null
  correct_count: number | null
  /** Сколько заданий выдано; у идущего теста — наибольшая возможная длина. */
  total: number
  started_at: string
  expires_at: string
  finished_at: string | null
}
export type Category = {
  specialization: string
  grade: string
  score: number
  /** Тест пройден с запасом: следующий грейд можно сдать досрочно. */
  upgrade_offer: boolean
  assigned_at: string
}
export type AssessmentState = {
  category: Category | null
  active: (Attempt & { position: number; min_total: number; question: Question }) | null
  history: Attempt[]
  /** available_from: null — тест на грейд можно начать сейчас. */
  grades: { grade: string; available_from: string | null }[]
  /** То же по каждой специализации: срок после провала действует только в той, по которой был тест. */
  grades_by_specialization: Record<string, { grade: string; available_from: string | null }[]>
  /** Стенд проверки: попытки можно сбросить и пройти тест заново. */
  demo_mode: boolean
}

export type InvitationStatus = 'sent' | 'viewed' | 'accepted' | 'declined'
export type CandidateCard = {
  candidate_id: number
  /** false — грейд заявлен, но последний тест на него не пройден. */
  verified: boolean
  specialization: string
  /** Подтверждённый грейд; для неподтверждённых — заявленный. */
  grade: string
  test_score: number
  stack: string[]
  matched_stack: string[]
  /** null — кандидат скрыл стаж. */
  experience_years: number | null
  city: string
  work_formats: string[]
  about: string
  category_assigned_at: string
  fsp_linked: boolean
  fsp_achievements: FspAchievement[]
  fsp_rank: string | null
  /** Итоговая оценка 0…100, по которой отсортирована выдача; null — грейд не подтверждён. */
  score: number | null
  breakdown: { key: string; label: string; value: number }[]
  /** Объяснение выдачи: доводы за (plus), против (minus) и сведения, не меняющие оценку (info). */
  reasons: { kind: 'plus' | 'minus' | 'info'; text: string }[]
  invitation_status: InvitationStatus | null
}

export type NeedInput = {
  title: string
  text: string
  specialization: string | null
  grade: string | null
  stack: string[]
  work_formats: string[]
  salary_from: number | null
  salary_to: number | null
}
export type Need = NeedInput & {
  id: number
  specialization: string
  grade: string
  created_at: string
  updated_at: string
}
export type ParsedNeed = Omit<NeedInput, 'title' | 'text'> & { notes: string[] }
export type Matches = {
  need: Need
  categories: { specialization: string; grade: string; exact: boolean; count: number }[]
  /** Размер подборки до уточняющих фильтров. */
  total: number
  candidates: CandidateCard[]
  /** Заявили запрошенный или смежный грейд, но не подтвердили его тестом. */
  unverified: CandidateCard[]
}

type InvitationBase = {
  id: number
  title: string
  message: string
  salary_from: number
  salary_to: number
  contact: string
  status: InvitationStatus
  created_at: string
  responded_at: string | null
}
export type EmployerInvitation = InvitationBase & {
  candidate_id: number
  specialization: string | null
  grade: string | null
  contacts: { full_name: string; email: string; phone: string; telegram: string } | null
}
export type CandidateInvitation = InvitationBase & {
  company_name: string
  company_industry: string
  company_description: string
  company_website: string
}

export type VacancyInput = {
  title: string
  description: string
  specialization: string | null
  grade: string | null
  stack: string[]
  work_formats: string[]
  /** Пустая строка — поле формы ещё не заполнено. */
  salary_from: number | string
  salary_to: number | string
  is_open: boolean
}
export type EmployerVacancy = VacancyInput & {
  id: number
  specialization: string
  grade: string
  created_at: string
  applications_total: number
  applications_new: number
}
export type CandidateVacancy = {
  id: number
  title: string
  description: string
  specialization: string
  grade: string
  stack: string[]
  work_formats: string[]
  salary_from: number
  salary_to: number
  created_at: string
  company_name: string
  company_industry: string
  company_description: string
  fits_category: boolean
  application_status: InvitationStatus | null
}
export type VacancyApplication = {
  id: number
  candidate_id: number
  specialization: string
  grade: string
  test_score: number
  stack: string[]
  /** null — кандидат скрыл стаж. */
  experience_years: number | null
  message: string
  status: InvitationStatus
  created_at: string
  contacts: { full_name: string; email: string; phone: string; telegram: string }
}
export type MyApplication = {
  id: number
  vacancy_id: number
  title: string
  company_name: string
  salary_from: number
  salary_to: number
  status: InvitationStatus
  created_at: string
  responded_at: string | null
}

export type EmployerChallenge = {
  id: number
  title: string
  text: string
  specialization: string
  is_open: boolean
  created_at: string
  answers_total: number
  answers_unrated: number
}
export type ChallengeAnswer = {
  id: number
  candidate_id: number
  grade: string | null
  test_score: number | null
  /** Можно ли пригласить автора: профиль опубликован и категория подтверждена. */
  in_bank: boolean
  text: string
  rating: number | null
  created_at: string
}
export type CandidateChallenge = {
  id: number
  title: string
  text: string
  specialization: string
  company_name: string
  created_at: string
}
export type MyAnswer = {
  id: number
  challenge_title: string
  company_name: string
  text: string
  rating: number | null
  created_at: string
}
