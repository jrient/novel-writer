import { onMounted, onUnmounted } from 'vue'

export interface ShortcutConfig {
  key: string
  ctrl?: boolean
  shift?: boolean
  alt?: boolean
  meta?: boolean
  handler: (e: KeyboardEvent) => void
  description?: string
}

/**
 * 全局快捷键 composable
 *
 * 用法示例:
 * ```ts
 * useGlobalShortcuts([
 *   { key: 'ArrowUp', ctrl: true, handler: () => prevChapter() },
 *   { key: 'ArrowDown', ctrl: true, handler: () => nextChapter() },
 * ])
 * ```
 */
export function useGlobalShortcuts(shortcuts: ShortcutConfig[]) {
  function handleKeydown(e: KeyboardEvent) {
    // 忽略输入框中的快捷键（除了特定的全局快捷键）
    const target = e.target as HTMLElement
    const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable

    for (const shortcut of shortcuts) {
      const keyMatch = e.key.toLowerCase() === shortcut.key.toLowerCase()
      const ctrlMatch = !!shortcut.ctrl === (e.ctrlKey || e.metaKey)
      const shiftMatch = !!shortcut.shift === e.shiftKey
      const altMatch = !!shortcut.alt === e.altKey

      if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
        // 对于 Ctrl+Space 和数字键，即使在输入框中也触发
        const isForceGlobal = shortcut.key === ' ' || /^\d$/.test(shortcut.key)

        if (!isInput || isForceGlobal) {
          e.preventDefault()
          shortcut.handler(e)
          return
        }
      }
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', handleKeydown)
  })

  onUnmounted(() => {
    document.removeEventListener('keydown', handleKeydown)
  })

  return {
    shortcuts,
  }
}

/**
 * 格式化快捷键描述
 */
export function formatShortcut(shortcut: ShortcutConfig): string {
  const parts: string[] = []
  if (shortcut.ctrl) parts.push('Ctrl')
  if (shortcut.shift) parts.push('Shift')
  if (shortcut.alt) parts.push('Alt')

  let keyName = shortcut.key
  // 转换特殊键名
  const keyMap: Record<string, string> = {
    ' ': 'Space',
    'ArrowUp': '↑',
    'ArrowDown': '↓',
    'ArrowLeft': '←',
    'ArrowRight': '→',
    'Enter': '↵',
    'Escape': 'Esc',
  }
  if (keyMap[shortcut.key]) {
    keyName = keyMap[shortcut.key]
  }
  parts.push(keyName)

  return parts.join('+')
}