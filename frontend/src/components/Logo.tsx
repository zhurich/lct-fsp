import logoDark from '../assets/logo-compact-dark.svg'
import logoLight from '../assets/logo-compact.svg'

// Соотношение сторон официального компактного логотипа (знак + «ФСП»).
const RATIO = 345 / 116

/** Логотип ФСП. Файлы не перекрашиваются: для тёмного фона берётся официальный вариант со светлыми буквами. */
export default function Logo({ height = 34, theme = 'light' }: { height?: number; theme?: 'light' | 'dark' }) {
  return (
    <img
      src={theme === 'dark' ? logoDark : logoLight}
      alt="Федерация спортивного программирования России"
      height={height}
      width={Math.round(height * RATIO)}
      style={{ display: 'block', flex: 'none' }}
    />
  )
}
