import { AnimatePresence, motion } from 'framer-motion'

const EVENT_CONFIG = {
  dust_storm: { icon: '▲', label: 'DISASTER', color: '#F0523D' },
  meteor_fall: { icon: '▲', label: 'DISASTER', color: '#F0523D' },
  enter_boss: { icon: '▲', label: 'CRITICAL', color: '#FF2F2F' },
  launch_jam: { icon: '◆', label: 'JAM', color: '#E9B44C' },
  ignition_success: { icon: '✓', label: 'LAUNCH', color: '#7FB069' },
  ship_crashed: { icon: '✕', label: 'CRASH', color: '#8E9497' },
  central_supply: { icon: '↓', label: 'SUPPLY', color: '#63C7C4' },
  betrayal: { icon: '!', label: 'BETRAY', color: '#E9B44C' },
  rank_locked: { icon: '#', label: 'RANK', color: '#E9B44C' },
  prayer_response: { icon: '◎', label: 'PRAYER', color: '#7FB069' },
  voice_command: { icon: '~', label: 'VOICE', color: '#63C7C4' },
  card_input: { icon: '□', label: 'CARD', color: '#8E9497' },
}

const CN_LABEL = {
  dust_storm: '月尘风暴',
  meteor_fall: '陨石坠落',
  enter_boss: '进入终局',
  launch_jam: '发射干扰',
  ignition_success: '升空成功',
  ship_crashed: '飞船坠毁',
  central_supply: '中央空投',
  betrayal: '背叛',
  rank_locked: '排名锁定',
  prayer_response: '祈愿回应',
  voice_command: '语音指令',
  card_input: '卡牌输入',
}

function formatTime(t) {
  if (!t) return '--:--:--'
  const d = new Date(t)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

// 合并连续同类事件：相同 event_type 在 10 秒内合并为一条，标注 ×N
function mergeEvents(events) {
  if (!events || events.length === 0) return []
  const merged = []
  let current = null
  for (const ev of events) {
    if (!ev || !ev._t) continue
    const sameType = current && current.event_type === ev.event_type
    const timeDiff = current && ev._t - current.firstTime
    if (sameType && timeDiff < 10000) {
      current.count++
      current.lastEv = ev
    } else {
      if (current) merged.push(current)
      current = { ...ev, count: 1, firstTime: ev._t, lastEv: ev }
    }
  }
  if (current) merged.push(current)
  return merged
}

export default function EventTimeline({ events }) {
  const merged = mergeEvents(events)

  return (
    <div className="flex flex-col h-full panel">
      {/* 头部 */}
      <div className="px-3 py-2 border-b border-white/5 flex items-center justify-between">
        <span className="text-label">实时事件 / BATTLEFIELD LOG</span>
        <span className="text-[7px] font-mono text-muted/50">{merged.length} 条</span>
      </div>

      {/* 事件时间轴 */}
      <div className="flex-1 overflow-y-auto px-2 py-1">
        <AnimatePresence initial={false}>
          {merged.length === 0 && (
            <div className="text-[10px] text-muted p-3 text-center font-sc">等待事件...</div>
          )}
          {merged.map((ev, i) => {
            const cfg = EVENT_CONFIG[ev.event_type] || { icon: '·', label: 'EVENT', color: '#8E9497' }
            const isLatest = i === 0
            const opacity = Math.max(0.35, 1 - i * 0.06)

            return (
              <motion.div
                key={ev._t}
                layout
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity, x: 0 }}
                exit={{ opacity: 0, height: 0 }}
                className="flex items-start gap-2 py-1.5 px-1 border-b border-white/[0.03]"
              >
                {/* 时间 */}
                <span className="text-[7px] font-mono text-muted/50 tabular-nums mt-0.5 whitespace-nowrap">
                  {formatTime(ev._t)}
                </span>

                {/* 图标 */}
                <span className="ev-icon text-[10px] font-mono" style={{ color: cfg.color }}>
                  {cfg.icon}
                </span>

                {/* 内容 */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span
                      className="text-[7px] font-mono font-semibold tracking-wider"
                      style={{ color: cfg.color }}
                    >
                      {cfg.label}
                    </span>
                    {ev.faction && (
                      <span className="text-[7px] font-mono text-muted">/ {ev.faction.toUpperCase()}</span>
                    )}
                    {ev.count > 1 && (
                      <span className="text-[7px] font-mono text-muted/70">×{ev.count}</span>
                    )}
                  </div>
                  <div
                    className="font-sc text-[10px] mt-0.5 font-medium"
                    style={{ color: isLatest ? 'var(--lunar-white)' : 'var(--muted-text)' }}
                  >
                    {ev.message || CN_LABEL[ev.event_type] || ev.event_type}
                  </div>
                </div>
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
