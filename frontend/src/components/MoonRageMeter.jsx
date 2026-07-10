import { motion } from 'framer-motion'

// 档位边界与后端一致：25 / 50 / 80
const TIER = {
  sleep: { c: '#00f2ff', label: '沉睡 SLEEP' },
  alert: { c: '#f1c40f', label: '警觉 ALERT' },
  anger: { c: '#f39c12', label: '愤怒 ANGER' },
  endgame: { c: '#ff4d4d', label: '终局 ENDGAME' },
}

const PHASE_CN = {
  draw: '摸牌',
  command: '指挥',
  action: '行动',
  combat: '对抗',
  moon: '月球',
  resolve: '结算',
}

export default function MoonRageMeter({ rage = 0, tier = 'sleep', phase, turn }) {
  const t = TIER[tier] || TIER.sleep
  return (
    <div className="text-center">
      <div className="flex items-baseline justify-center gap-3">
        <span className="text-xs tracking-[0.3em] text-white/50">MOON RAGE</span>
        <span
          className="text-3xl font-black tabular-nums"
          style={{ color: t.c, textShadow: `0 0 12px ${t.c}` }}
        >
          {Math.round(rage)}
        </span>
        <span className="text-xs font-bold" style={{ color: t.c }}>
          {t.label}
        </span>
      </div>

      <div className="mt-1 h-3 w-full rounded-full bg-white/5 overflow-hidden border border-white/10">
        <motion.div
          className="h-full rounded-full"
          animate={{ width: `${Math.max(0, Math.min(100, rage))}%` }}
          transition={{ type: 'spring', stiffness: 80, damping: 20 }}
          style={{ background: `linear-gradient(90deg, #00f2ff, ${t.c})`, boxShadow: `0 0 14px ${t.c}` }}
        />
      </div>

      {/* 档位刻度 */}
      <div className="relative h-3 text-[9px] text-white/30">
        {[25, 50, 80].map((v) => (
          <span key={v} className="absolute -translate-x-1/2" style={{ left: `${v}%` }}>
            {v}
          </span>
        ))}
      </div>

      <div className="mt-1 text-xs text-white/60">
        回合 {turn ?? '-'} · {PHASE_CN[phase] || phase || '-'} 阶段
      </div>
    </div>
  )
}
