import { motion, AnimatePresence } from 'framer-motion'

// 5档狂暴色阶：稳定→活跃→愤怒→狂暴→失控
const RAGE_TIERS = [
  { max: 25, color: '#8E9497', en: 'STABLE', cn: '稳定' },
  { max: 50, color: '#E9B44C', en: 'ACTIVE', cn: '活跃' },
  { max: 80, color: '#F0523D', en: 'ANGER', cn: '愤怒' },
  { max: 95, color: '#FF2F2F', en: 'BERSERK', cn: '狂暴' },
  { max: 101, color: '#FF2F2F', en: 'OUT OF CONTROL', cn: '失控', flash: true },
]

function rageTier(rage) {
  return RAGE_TIERS.find((t) => rage < t.max) || RAGE_TIERS[0]
}

const PHASE_CODE = {
  sleep: 'PHASE 01',
  alert: 'PHASE 02',
  anger: 'PHASE 03',
  endgame: 'PHASE 04',
}

const PHASE_CN = {
  draw: '摸牌',
  command: '指挥',
  action: '行动',
  combat: '对抗',
  moon: '月球',
  resolve: '结算',
}

export default function TopBar({ rage = 0, tier = 'sleep', phase, turn, status, factions = [] }) {
  const rt = rageTier(rage)
  const statusColor = status === 'live' ? '#63C7C4' : status === 'mock' ? '#E9B44C' : '#8E9497'
  const statusLabel = status === 'live' ? '● LIVE' : status === 'mock' ? '○ MOCK' : '… 连接中'

  // 心率压力贡献：各玩家心率对狂暴度的贡献百分比
  const stressValues = factions.map((f) => {
    const hr = f.vars?.heart_rate || 0
    return Math.max(0, hr - 60) // 基线 60 BPM
  })
  const totalStress = stressValues.reduce((s, v) => s + v, 0) || 1

  return (
    <div className="relative flex flex-col panel-strong z-30 border-b border-white/5">
      <div className="flex items-center h-[52px] px-5">
        {/* 左：阶段标识 */}
        <div className="flex items-center gap-3 w-[160px] flex-shrink-0">
          <div className="flex flex-col">
            <span className="text-[8px] font-mono text-muted tracking-[0.15em]">{PHASE_CODE[tier]}</span>
            <span className="font-condensed text-base font-bold leading-none" style={{ color: rt.color }}>
              {rt.cn}
            </span>
          </div>
          <div className="w-px h-7 bg-white/10" />
          <div className="flex flex-col">
            <span className="text-[8px] font-mono text-muted tracking-[0.15em]">TURN</span>
            <span className="font-condensed text-base font-bold text-lunar-white leading-none tabular-nums">
              {turn ?? '-'}
            </span>
          </div>
        </div>

        {/* 中：月球狂暴度 */}
        <div className="flex-1 mx-6">
          <div className="flex items-center gap-3">
            <span className="text-[8px] font-mono text-muted whitespace-nowrap">月球狂暴度</span>
            <span className="font-condensed text-2xl font-bold tabular-nums leading-none" style={{ color: rt.color }}>
              {Math.round(rage)}
            </span>
            <span className="text-[9px] font-mono font-semibold tracking-wider" style={{ color: rt.color }}>
              {rt.en}
            </span>
            <div className="flex-1 h-[6px] bg-white/5 overflow-hidden relative">
              <motion.div
                className={`h-full ${rt.flash ? 'animate-flicker' : ''}`}
                animate={{ width: `${Math.max(0, Math.min(100, rage))}%` }}
                transition={{ type: 'spring', stiffness: 60, damping: 20 }}
                style={{ background: rt.color }}
              />
              {/* 档位刻度线 */}
              {[25, 50, 80].map((v) => (
                <div
                  key={v}
                  className="absolute top-0 bottom-0 w-px bg-white/20"
                  style={{ left: `${v}%` }}
                />
              ))}
            </div>
          </div>

          {/* 心率压力贡献条 */}
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[7px] font-mono text-muted/60 whitespace-nowrap">心率压力贡献</span>
            <div className="flex-1 h-[3px] flex overflow-hidden">
              {factions.map((f, i) => {
                const pct = (stressValues[i] / totalStress) * 100
                const fcolors = ['#63C7C4', '#E9B44C', '#7FB069', '#B08FC7']
                return (
                  <div
                    key={f.id}
                    className="h-full transition-all duration-500"
                    style={{ width: `${pct}%`, background: fcolors[i] || '#8E9497' }}
                  />
                )
              })}
            </div>
            <div className="flex gap-1.5">
              {factions.map((f, i) => {
                const pct = Math.round((stressValues[i] / totalStress) * 100)
                if (pct === 0) return null
                const fcolors = ['#63C7C4', '#E9B44C', '#7FB069', '#B08FC7']
                return (
                  <span key={f.id} className="text-[7px] font-mono tabular-nums" style={{ color: fcolors[i] }}>
                    {f.id.toUpperCase()}{pct}%
                  </span>
                )
              })}
            </div>
          </div>
        </div>

        {/* 右：连接状态 */}
        <div className="flex items-center gap-3 w-[120px] flex-shrink-0 justify-end">
          <span className="text-[8px] font-mono" style={{ color: statusColor }}>{statusLabel}</span>
          <span className="text-[9px] font-mono text-muted/50">MOONFALL</span>
        </div>
      </div>

      {/* 终局危险条 */}
      <AnimatePresence>
        {tier === 'endgame' && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 2 }}
            exit={{ height: 0 }}
            className="danger-bar w-full animate-pulse-warn"
          />
        )}
      </AnimatePresence>
    </div>
  )
}
