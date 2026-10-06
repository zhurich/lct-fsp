import { createTheme, type MantineColorsTuple } from '@mantine/core'

// Тема Mantine по дизайн-системе ФСП России. Значения взяты из токенов (styles/tokens.css):
// брендовые цвета стоят на шестой позиции шкалы — её Mantine использует для заливки.
const blue: MantineColorsTuple = [
  '#F4F3FF', '#E6E3FF', '#C9C3FF', '#9E94FF', '#7A6DFF', '#5C4DFF', '#402FFF', '#3221E6', '#2618BF', '#140C66',
]
const red: MantineColorsTuple = [
  '#FEF2F3', '#FCDDE1', '#F9B9C1', '#F58E9B', '#F16072', '#EE3A4F', '#EC1D35', '#CF1028', '#A80C20', '#6E0815',
]
// Серые тона и «чернила»: шестая позиция — вторичный текст (ink-500), девятая — основной (ink-900).
const gray: MantineColorsTuple = [
  '#F6F6F6', '#EDEDED', '#DCDDDE', '#C8C9CA', '#9A9BA0', '#7C7D84', '#5F6068', '#4A4B53', '#34353C', '#1B1C21',
]
// Статусные цвета: на шестой позиции — тёмный тон для текста на светлой подложке (как у бейджей системы).
const green: MantineColorsTuple = [
  '#E9F6EF', '#CDEBDB', '#A5DBC0', '#78C9A1', '#4FB783', '#1E9E5A', '#157A44', '#126A3B', '#0D4F2C', '#08361E',
]
const yellow: MantineColorsTuple = [
  '#FDF4E1', '#FBE8BF', '#F7D68F', '#F2C25C', '#E6A420', '#D98E04', '#8A5A00', '#7A4F00', '#5C3C00', '#3D2800',
]

const FONT = '"JetBrains Mono", ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace'

export const theme = createTheme({
  colors: { blue, red, gray, green, yellow },
  primaryColor: 'blue',
  primaryShade: 6,
  black: '#1B1C21',
  white: '#FFFFFF',

  // Единственный шрифт бренда — JetBrains Mono.
  fontFamily: FONT,
  fontFamilyMonospace: FONT,
  fontSizes: { xs: '12px', sm: '14px', md: '16px', lg: '18px', xl: '20px' },
  lineHeights: { xs: '1.4', sm: '1.5', md: '1.55', lg: '1.55', xl: '1.3' },
  headings: {
    fontFamily: FONT,
    fontWeight: '500',
    sizes: {
      h1: { fontSize: '44px', lineHeight: '1.15' },
      h2: { fontSize: '34px', lineHeight: '1.15' },
      h3: { fontSize: '26px', lineHeight: '1.3', fontWeight: '600' },
      h4: { fontSize: '20px', lineHeight: '1.3', fontWeight: '600' },
    },
  },

  // Сдержанные радиусы: 2px — бейджи и чекбоксы, 4px — кнопки и поля, 8px — карточки и диалоги.
  radius: { xs: '2px', sm: '4px', md: '8px', lg: '12px', xl: '20px' },
  defaultRadius: 'sm',
  // Тени — только у всплывающих слоёв.
  shadows: {
    xs: '0 1px 2px rgba(27, 28, 33, 0.08)',
    sm: '0 1px 2px rgba(27, 28, 33, 0.08)',
    md: '0 6px 20px rgba(27, 28, 33, 0.10)',
    lg: '0 18px 48px rgba(27, 28, 33, 0.18)',
    xl: '0 18px 48px rgba(27, 28, 33, 0.18)',
  },

  components: {
    Button: { defaultProps: { fw: 600 } },
    Paper: { defaultProps: { radius: 'md' } },
    Alert: { defaultProps: { radius: 'md' } },
    // Бейдж системы: прямоугольный, без капса.
    Badge: { defaultProps: { radius: 'xs', tt: 'none', fw: 600 } },
    Checkbox: { defaultProps: { radius: 'xs' } },
    Progress: { defaultProps: { radius: 'xs' } },
    Modal: {
      defaultProps: {
        radius: 'md',
        centered: true,
        // Без размытия: backdrop-filter поверх длинной страницы подвешивает открытие и закрытие.
        overlayProps: { color: '#1B1C21', backgroundOpacity: 0.64 },
      },
    },
    Notification: { defaultProps: { radius: 'md' } },
    Anchor: { defaultProps: { underline: 'hover' } },
  },
})
