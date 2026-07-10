import { memo } from 'react'
import { motion } from 'framer-motion'
import { factionColor } from '../lib/factions'
import { THEME_STYLE, ZONE_ICON } from '../themes'

// 区域按 kind 上色。位置(center)来自 /api/config；是否激活/强度来自实时 state.world。
const KIND_COLOR = {
  base: '#00f2ff',
  resource: '#a29bfe',
  relic: '#2ecc71',
  hazard: '#bbbbbb',
  obstacle: '#ff4d4d',
  trap: '#f39c12',
}

function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`
}

function MapGridBase({ config, units, zones, tier, theme }) {
  const ts = THEME_STYLE[theme] || THEME_STYLE.lunar
  const grid = config.map?.grid || [12, 12]
  const gw = grid[0]
  const gh = grid[1]
  const cell = 52
  const W = gw * cell
  const H = gh * cell
  const liveById = Object.fromEntries((zones || []).map((z) => [z.id, z]))
  const cfgZones = config.map?.zones || []
  const angry = tier === 'anger' || tier === 'endgame'

  return (
    <div className="map-stage p-2" style={{ boxShadow: ts.glow ? '0 0 40px rgba(0,242,255,0.12)' : 'none' }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ maxHeight: '66vh', maxWidth: '46vw' }}>
        {/* 底格 */}
        {Array.from({ length: gw * gh }).map((_, i) => {
          const x = (i % gw) * cell
          const y = Math.floor(i / gw) * cell
          return (
            <rect
              key={i}
              x={x + 1}
              y={y + 1}
              width={cell - 2}
              height={cell - 2}
              fill="transparent"
              style={{ stroke: 'var(--grid)' }}
            />
          )
        })}

        {/* 区域 */}
        {cfgZones.map((z) => {
          const center = z.center || [0, 0]
          const cx = center[0] * cell
          const cy = center[1] * cell
          const color = KIND_COLOR[z.kind] || '#a29bfe'
          const dynamic = !!z.dynamic
          const live = liveById[z.id] || {}
          const active = dynamic ? !!live.active : true
          if (dynamic && !active) return null
          const intensity = live.intensity != null ? live.intensity : z.intensity != null ? z.intensity : 1
          const size = cell * 1.7
          const opacity = dynamic ? 0.3 + intensity * 0.5 : 0.55
          return (
            <g key={z.id}>
              <motion.rect
                initial={{ opacity: 0 }}
                animate={{ opacity }}
                transition={{ duration: 0.5 }}
                x={cx - size / 2}
                y={cy - size / 2}
                width={size}
                height={size}
                rx={ts.zoneRadius}
                fill={hexA(color, ts.glow ? 0.14 : 0.28)}
                stroke={color}
                strokeWidth={theme === 'pixel' ? 3 : 1.5}
                style={ts.glow ? { filter: `drop-shadow(0 0 8px ${hexA(color, 0.5)})` } : undefined}
                className={dynamic && angry ? 'animate-pulse' : ''}
              />
              <text x={cx} y={cy - 4} textAnchor="middle" fontSize="20">
                {ZONE_ICON[z.kind] || '◆'}
              </text>
              <text x={cx} y={cy + 20} textAnchor="middle" fontSize="11" fill={color} opacity="0.9">
                {z.name || z.id}
              </text>
            </g>
          )
        })}

        {/* 小机器人 */}
        {units.map((u) => {
          const color = factionColor(u.faction)
          const pose = u.pose || { x: 0, y: 0, theta: 0 }
          const tx = pose.x * cell
          const ty = pose.y * cell
          const deg = ((pose.theta || 0) * 180) / Math.PI + 90
          const glow = ts.glow ? { filter: `drop-shadow(0 0 7px ${color})` } : undefined
          return (
            <motion.g
              key={u.id}
              animate={{ x: tx, y: ty }}
              transition={{ type: 'spring', stiffness: 55, damping: 18 }}
            >
              {ts.unitShape === 'block' ? (
                <rect x="-9" y="-9" width="18" height="18" fill={color} stroke="#000" strokeWidth="2" style={glow} />
              ) : ts.unitShape === 'round' ? (
                <g transform={`rotate(${deg})`}>
                  <circle r="9" fill={color} />
                  <path d="M 0 -12 L 6 -4 L -6 -4 Z" fill={color} />
                </g>
              ) : (
                <g transform={`rotate(${deg})`}>
                  <path d="M 0 -13 L 10 10 L -10 10 Z" fill={color} stroke="#05070a" strokeWidth="1" style={glow} />
                </g>
              )}
              {u.carrying ? (
                <circle r="5" cx="0" cy="0" fill="#a29bfe" style={ts.glow ? { filter: 'drop-shadow(0 0 6px #a29bfe)' } : undefined} />
              ) : null}
              <text x="0" y="26" textAnchor="middle" fontSize="10" fill={color}>
                {u.id}
              </text>
            </motion.g>
          )
        })}
      </svg>
    </div>
  )
}

export default memo(MapGridBase)
