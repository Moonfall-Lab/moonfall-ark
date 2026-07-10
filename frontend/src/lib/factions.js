// 四个阵营的主题色
export const FACTION_COLORS = {
  pa: '#00f2ff', // 冰河蓝
  pb: '#a29bfe', // 荧光紫
  pc: '#f39c12', // 警示橙
  pd: '#2ecc71', // 荧光绿
}

export const factionColor = (id) => FACTION_COLORS[id] || '#8899aa'
