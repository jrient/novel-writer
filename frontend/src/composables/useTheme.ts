/**
 * 深色模式管理
 * 使用 @vueuse/core 的 useDark 实现
 */
import { useDark, useToggle } from '@vueuse/core'

// 深色模式状态（自动同步到 html.dark 类）
export const isDark = useDark({
  selector: 'html',
  attribute: 'class',
  valueDark: 'dark',
  valueLight: '',
  storageKey: 'novel-writer-theme',
})

// 切换深色模式
export const toggleDark = useToggle(isDark)

/**
 * 深色模式 composable
 */
export function useTheme() {
  /**
   * 设置主题
   */
  function setTheme(dark: boolean) {
    isDark.value = dark
  }

  /**
   * 跟随系统主题
   */
  function followSystem() {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    setTheme(prefersDark)
  }

  /**
   * 监听系统主题变化
   */
  function watchSystemTheme() {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => {
      setTheme(e.matches)
    }
    mediaQuery.addEventListener('change', handler)
    return () => mediaQuery.removeEventListener('change', handler)
  }

  return {
    isDark,
    toggleDark,
    setTheme,
    followSystem,
    watchSystemTheme,
  }
}