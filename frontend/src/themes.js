// 三套皮肤。视觉差异主要靠 index.css 的 [data-theme] 变量，
// 这里放结构性差异（区域/小车形状、发光开关、图标）。

export const THEMES = [
  { key: 'lunar', label: '写实月面' },
  { key: 'pixel', label: '复古像素' },
]

export const THEME_STYLE = {
  lunar: { glow: true, zoneRadius: 8, unitShape: 'chevron', scanlines: true },
  pixel: { glow: false, zoneRadius: 0, unitShape: 'block', scanlines: false },
}

// 区域图标（emoji 占位，之后可替换为贴图）
export const ZONE_ICON = {
  base: '🚀',
  resource: '⛽',
  relic: '💎',
  hazard: '🌫️',
  obstacle: '☄️',
  trap: '⚡',
}
