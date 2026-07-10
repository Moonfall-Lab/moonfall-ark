// 四个阵营的主题色 — 月尘工业色系（降低饱和度，仅用于识别条）
export const FACTION_COLORS = {
  pa: '#63C7C4', // 工业青
  pb: '#E9B44C', // 警示琥珀
  pc: '#7FB069', // 苔藓绿
  pd: '#B08FC7', // 低饱和紫
}

export const factionColor = (id) => FACTION_COLORS[id] || '#8E9497'

export const FACTION_LABELS = {
  pa: 'A',
  pb: 'B',
  pc: 'C',
  pd: 'D',
}
