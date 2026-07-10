import { motion } from 'framer-motion'
import { factionColor } from '../lib/factions'
import HeartRateWave from './HeartRateWave'

// 单个玩家飞船面板。数据全部来自 state.world 的 faction.vars。
// 外观(背景/圆角/模糊/阴影/字体)由 .panel 类按主题变化。
export default function PlayerPanel({ faction, config, unit, corner }) {
  if (!faction) return <div className="w-64" />

  const color = factionColor(faction.id)
  const v = faction.vars || {}
  const fuel = v.fuel ?? 0
  const shipHp = v.ship_hp ?? 0
  const hr = v.heart_rate ?? 0
  const jammed = (v.jammed ?? 0) > 0
  const igniting = (v.declaring_launch ?? 0) > 0
  const launched = (v.launched ?? 0) > 0
  const crashed = (v.crashed ?? 0) > 0
  const shielded = (v.shield ?? 0) > 0

  const name = (config.factions || []).find((f) => f.id === faction.id)?.name || faction.id.toUpperCase()
  const right = corner.endsWith('right')

  return (
    <motion.div
      layout
      className={`panel pointer-events-auto w-64 p-4 ${right ? 'text-right' : 'text-left'} ${
        jammed ? 'animate-shake' : ''
      } ${crashed ? 'opacity-40 grayscale' : ''}`}
      style={{
        boxShadow: `var(--panel-shadow) ${color}33`,
        [right ? 'borderRight' : 'borderLeft']: `4px solid ${color}`,
      }}
    >
      <div className={`flex items-end gap-3 mb-3 ${right ? 'flex-row-reverse' : ''}`}>
        <h2 className="title-font text-lg font-extrabold tracking-tight leading-none" style={{ color }}>
          {name}
        </h2>
        {faction.rank ? <div className="title-font text-2xl font-black" style={{ color: 'var(--accent)' }}>#{faction.rank}</div> : null}
      </div>

      {/* 燃料槽 5 格 */}
      <div className={`flex gap-1.5 mb-3 ${right ? 'flex-row-reverse' : ''}`}>
        {Array.from({ length: 5 }).map((_, i) => (
          <div
            key={i}
            className="h-5 flex-1 rounded-sm"
            style={
              i < fuel
                ? { background: '#a29bfe', boxShadow: '0 0 10px #a29bfe' }
                : { background: 'rgba(255,255,255,0.07)' }
            }
          />
        ))}
      </div>

      {/* 船血 + 心率 */}
      <div className={`flex items-center justify-between gap-2 ${right ? 'flex-row-reverse' : ''}`}>
        <div className={`flex gap-1 ${right ? 'flex-row-reverse' : ''}`}>
          {Array.from({ length: 3 }).map((_, i) => (
            <svg key={i} width="18" height="18" viewBox="0 0 24 24">
              <path
                d="M12 21s-8-5.3-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 10c0 5.7-8 11-8 11z"
                fill={i < shipHp ? '#ff4d4d' : 'transparent'}
                stroke="#ff4d4d"
                strokeWidth="1.5"
              />
            </svg>
          ))}
        </div>
        <div className={`flex flex-col ${right ? 'items-start' : 'items-end'}`}>
          <span className="muted text-[9px] uppercase tracking-widest">Heart</span>
          <span className="text-base font-bold text-emerald-400">
            {hr ? hr : '--'}
            <span className="text-[10px]"> BPM</span>
          </span>
        </div>
      </div>

      {/* 心率波形 */}
      <div className="mt-2">
        <HeartRateWave bpm={hr} color={color} />
      </div>

      {/* 状态徽章 */}
      <div className={`mt-2 h-5 flex gap-1.5 text-[10px] ${right ? 'justify-end' : ''}`}>
        {igniting && !launched ? <span className="bg-lava px-2 py-0.5 rounded animate-pulse">IGNITION</span> : null}
        {jammed ? <span className="bg-warn text-black px-2 py-0.5 rounded">JAMMED</span> : null}
        {shielded ? <span className="bg-glacier text-black px-2 py-0.5 rounded">SHIELD</span> : null}
        {launched ? <span className="bg-emerald-600 px-2 py-0.5 rounded">LAUNCHED</span> : null}
        {crashed ? <span className="bg-gray-600 px-2 py-0.5 rounded">CRASHED</span> : null}
      </div>
    </motion.div>
  )
}
