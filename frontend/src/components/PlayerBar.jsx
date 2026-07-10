import { motion, AnimatePresence } from 'framer-motion'
import { factionColor } from '../lib/factions'

const PLAYER_ART = {
  pa: '/assets/ui/players/pa.png',
  pb: '/assets/ui/players/pb.png',
  pc: '/assets/ui/players/pc.png?v=2',
  pd: '/assets/ui/players/pd.png',
}

// 心率分级颜色
function hrColor(hr) {
  if (!hr || hr < 100) return '#E7E1D6'
  if (hr < 120) return '#E9B44C'
  if (hr < 140) return '#F0523D'
  return '#FF2F2F'
}

// 玩家当前行为
function currentAction(unit, faction) {
  if (!unit) return '待命'
  if (faction?.vars?.launched) return '已升空'
  if (faction?.vars?.crashed) return '已坠毁'
  if (faction?.vars?.jammed > 0) return '受干扰'
  if (unit.carrying) return '搬运资源'
  if (unit.status === 'collect') return '采集资源'
  if (unit.status === 'return') return '返回基地'
  return '待命'
}

// 状态标记（去掉"已升空"，因为 action 里已经显示了）
function statusMarks(faction) {
  const v = faction?.vars || {}
  const marks = []
  if (v.declaring_launch > 0 && !v.launched) marks.push({ text: '点火', color: '#E9B44C' })
  if (v.jammed > 0) marks.push({ text: '干扰', color: '#F0523D' })
  if (v.shield > 0) marks.push({ text: '护盾', color: '#63C7C4' })
  if (v.crashed) marks.push({ text: '坠毁', color: '#8E9497' })
  return marks
}

export default function PlayerBar({ faction, config, unit, stressPct = 0 }) {
  if (!faction) return null

  const color = factionColor(faction.id)
  const v = faction.vars || {}
  const hr = v.heart_rate ?? 0
  const fuel = v.fuel ?? 0
  const shipHp = v.ship_hp ?? 0
  const name = (config.factions || []).find((f) => f.id === faction.id)?.name || faction.id.toUpperCase()
  const action = currentAction(unit, faction)
  const marks = statusMarks(faction)
  const crashed = v.crashed > 0
  const hrCol = hrColor(hr)
  const highStress = hr >= 120

  return (
    <motion.div
      layout
      className={`panel relative flex items-stretch overflow-hidden ${crashed ? 'opacity-40' : ''} ${highStress ? 'border-l-2' : ''}`}
      style={highStress ? { borderLeftColor: hrCol } : {}}
    >
      {/* 左侧色条 */}
      <div className="w-[3px] flex-shrink-0" style={{ background: color }} />

      <div
        className="telemetry-portrait relative my-1.5 ml-1.5 w-9 flex-shrink-0 overflow-hidden border border-white/[0.07] bg-black/20"
        style={{ borderRightColor: color }}
      >
        {PLAYER_ART[faction.id] ? (
          <img
            src={PLAYER_ART[faction.id]}
            alt=""
            className="absolute inset-0 h-full w-full scale-[1.4] object-cover object-top opacity-85 brightness-110 contrast-115"
          />
        ) : (
          <div className="flex h-full flex-col items-center justify-center opacity-45" style={{ color }}>
            <div className="h-5 w-5 rounded-full border border-current" />
            <div className="-mt-px h-3 w-7 rounded-t-lg border-x border-t border-current" />
            <span className="mt-1 font-mono text-[7px]">{faction.id.toUpperCase()}</span>
          </div>
        )}
        {/* 右侧玩家色竖线 */}
        <div className="absolute right-0 top-0 bottom-0 w-[2px]" style={{ background: color, opacity: 0.7 }} />
      </div>

      <div className="flex-1 px-2.5 py-1.5">
        {/* 第一行：代号 + 名称 + 心率 */}
        <div className="flex items-center justify-between">
          <div className="flex items-baseline gap-1.5">
            <span className="font-condensed text-sm font-bold leading-none" style={{ color }}>
              {faction.id.toUpperCase()}
            </span>
            <span className="font-sc text-[9px] text-muted leading-none">{name}</span>
            {faction.rank ? (
              <span className="text-[8px] text-muted font-mono leading-none">#{faction.rank}</span>
            ) : null}
          </div>
          <div className="flex items-baseline gap-1">
            <span className="font-condensed text-lg font-bold tabular-nums leading-none" style={{ color: hrCol }}>
              {hr || '--'}
            </span>
            <span className="text-[7px] text-muted leading-none">BPM</span>
          </div>
        </div>

        {/* 第二行：当前行为 + 狂暴贡献 */}
        <div className="flex items-center justify-between mt-0.5">
          <div className="flex items-center gap-1.5">
            <span className="font-sc text-[10px] font-medium" style={{ color: 'var(--lunar-white)' }}>
              {action}
            </span>
          </div>
          {stressPct > 5 && (
            <span className="text-[7px] font-mono" style={{ color: hr >= 120 ? hrCol : 'var(--muted-text)' }}>
              狂暴贡献 {stressPct}%
            </span>
          )}
        </div>

        {/* 第三行：ENERGY 燃料 + DAMAGE 船血（带标签） */}
        <div className="flex items-center justify-between mt-1 gap-2">
          <div className="flex items-center gap-1">
            <span className="text-[6px] font-mono text-muted">FUEL</span>
            <div className="flex gap-[2px]">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="w-1.5 h-2"
                  style={{ background: i < fuel ? '#E9B44C' : 'rgba(255,255,255,0.06)' }}
                />
              ))}
            </div>
          </div>
          <div className="flex items-center gap-1">
            <span className="text-[6px] font-mono text-muted">HULL</span>
            <div className="flex gap-[2px]">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="w-1.5 h-2"
                  style={{ background: i < shipHp ? '#F0523D' : 'rgba(255,255,255,0.06)' }}
                />
              ))}
            </div>
          </div>
        </div>

        {/* 状态标记 */}
        {marks.length > 0 && (
          <div className="flex gap-1 mt-0.5">
            {marks.map((m, i) => (
              <span
                key={i}
                className="text-[7px] px-1 font-mono"
                style={{ color: m.color, borderLeft: `2px solid ${m.color}` }}
              >
                {m.text}
              </span>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  )
}
