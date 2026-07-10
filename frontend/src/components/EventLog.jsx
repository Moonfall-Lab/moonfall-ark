import { motion, AnimatePresence } from 'framer-motion'

const LABEL = {
  dust_storm: '月尘风暴',
  meteor_fall: '陨石坠落',
  central_supply: '中央空投',
  launch_jam: '发射干扰',
  ignition_success: '升空成功',
  ship_crashed: '飞船坠毁',
  betrayal: '背叛',
  rank_locked: '排名锁定',
  enter_boss: '进入终局',
  prayer_response: '祈愿回应',
  voice_command: '语音指令',
  card_input: '卡牌',
}

const COLOR = {
  ignition_success: '#2ecc71',
  ship_crashed: '#ff4d4d',
  enter_boss: '#ff4d4d',
  meteor_fall: '#ff4d4d',
  betrayal: '#f39c12',
  launch_jam: '#f39c12',
  dust_storm: '#bbbbbb',
}

export default function EventLog({ events }) {
  return (
    <div className="h-full flex flex-col">
      <div className="text-xs tracking-[0.3em] text-white/40 mb-2 text-right">EVENT FEED</div>
      <div className="flex-1 overflow-hidden flex flex-col gap-1.5">
        <AnimatePresence initial={false}>
          {events.map((ev, i) => {
            const c = COLOR[ev.event_type] || '#00f2ff'
            return (
              <motion.div
                key={ev._t}
                layout
                initial={{ opacity: 0, x: 40 }}
                animate={{ opacity: Math.max(0.25, 1 - i * 0.07), x: 0 }}
                exit={{ opacity: 0, height: 0 }}
                className="bg-black/50 border-r-2 px-3 py-1.5 text-right"
                style={{ borderColor: c }}
              >
                <span className="text-xs font-bold" style={{ color: c }}>
                  {LABEL[ev.event_type] || ev.event_type}
                </span>
                {ev.message ? <div className="text-white/70 text-[11px]">{ev.message}</div> : null}
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
