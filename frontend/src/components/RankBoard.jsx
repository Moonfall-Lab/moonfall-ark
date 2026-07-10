import { motion, AnimatePresence } from 'framer-motion'

// 已升空玩家按名次展示，营造结算仪式感。
export default function RankBoard({ factions, config }) {
  const ranked = (factions || [])
    .filter((f) => f.rank)
    .sort((a, b) => a.rank - b.rank)
  const nameOf = (id) => (config.factions || []).find((f) => f.id === id)?.name || id

  return (
    <div>
      <div className="text-xs tracking-[0.3em] text-white/40 mb-2">RANKING</div>
      <div className="flex flex-col gap-1.5">
        {ranked.length === 0 ? <div className="text-white/30 text-xs">尚无升空</div> : null}
        <AnimatePresence initial={false}>
          {ranked.map((f) => (
            <motion.div
              key={f.id}
              layout
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              className="flex items-center gap-2 bg-black/50 px-2 py-1 border-l-2 border-warn"
            >
              <span className="text-warn font-black text-lg">#{f.rank}</span>
              <span className="text-sm">{nameOf(f.id)}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}
