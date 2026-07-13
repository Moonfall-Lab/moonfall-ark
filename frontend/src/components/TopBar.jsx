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

const MOON_ART = {
  sleep: '/assets/ui/moon/stable.png',
  alert: '/assets/ui/moon/active.png',
  anger: '/assets/ui/moon/angry.png',
  endgame: '/assets/ui/moon/angry.png',
}

export default function TopBar({ rage = 0, tier = 'sleep', phase, turn, status, factions = [], currentPlayerId, onNextTurn }) {
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
      <div className="flex items-center h-[60px] px-5">
        {/* 左：阶段标识 */}
        <div className="flex items-center gap-3 w-[140px] flex-shrink-0">
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

        {/* 月球状态舱位：独立容器，有上下留白 */}
        <div className="flex items-center gap-3 flex-shrink-0">
          <div className="w-px h-8 bg-white/10" />
          <div className="flex flex-col items-center justify-center" style={{ width: 52, height: 52, padding: 6 }}>
            <div className="relative w-full h-full overflow-hidden rounded-full bg-black/40 telemetry-moon" style={{ border: `1px solid rgba(255,255,255,${tier === 'endgame' ? 0.15 : 0.06})` }}>
              <AnimatePresence mode="wait" initial={false}>
                <motion.img
                  key={tier}
                  src={MOON_ART[tier] || MOON_ART.sleep}
                  alt=""
                  initial={{ opacity: 0, scale: 1.15 }}
                  animate={{ opacity: 0.8, scale: 1.3 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 h-full w-full object-cover grayscale-[0.4] saturate-60 brightness-90 contrast-115"
                />
              </AnimatePresence>
              {/* 机械眼 */}
              <motion.div
                className="absolute top-[35%] left-[35%] h-1.5 w-1.5 rounded-full"
                animate={{ opacity: [0.4, 1, 0.4] }}
                transition={{ duration: tier === 'endgame' ? 0.8 : 3, repeat: Infinity }}
                style={{ background: rt.color, boxShadow: `0 0 4px ${rt.color}` }}
              />
              <div className="absolute inset-0 rounded-full shadow-[inset_0_0_8px_rgba(0,0,0,0.6)]" />
            </div>
          </div>
          <div className="flex flex-col">
            <span className="text-[7px] font-mono text-muted/60 tracking-[0.15em]">LUNAR AI</span>
          </div>
          <div className="w-px h-8 bg-white/10" />
        </div>

        {/* 中：当前识别玩家 */}
        <div className="flex-1 mx-4">
          <div className="flex items-center gap-3">
            <span className="text-[8px] font-mono text-muted whitespace-nowrap">当前识别玩家</span>
            <span className="font-condensed text-2xl font-bold tabular-nums leading-none" style={{ color: '#E9B44C' }}>
              {(currentPlayerId || 'p1').toUpperCase()}
            </span>
            <span className="text-[9px] font-mono font-semibold tracking-wider" style={{ color: '#63C7C4' }}>
              请扫描卡牌
            </span>
            <button type="button" className="debug-btn ml-auto" onClick={onNextTurn}>
              下一回合
            </button>
          </div>

          <div className="mt-1 flex items-center gap-2">
            <span className="text-[7px] font-mono text-muted/60 whitespace-nowrap">回合流程</span>
            <div className="h-[3px] flex-1 overflow-hidden bg-white/5">
              <div
                className="h-full transition-all duration-300"
                style={{ width: currentPlayerId === 'p2' ? '100%' : '50%', background: '#E9B44C' }}
              />
            </div>
            <span className="text-[7px] font-mono text-muted/60">A → B</span>
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
