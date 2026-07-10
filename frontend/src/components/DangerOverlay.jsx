import { motion } from 'framer-motion'

export default function DangerOverlay() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="absolute inset-0 pointer-events-none z-40"
    >
      <div className="absolute inset-0 border-[6px] border-lava/60 animate-pulse" />
      <motion.div
        className="absolute top-24 left-1/2 -translate-x-1/2 text-lava font-black text-2xl tracking-[0.4em] whitespace-nowrap"
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 1.2, repeat: Infinity }}
      >
        ⚠ ENDGAME · 终局狂暴 ⚠
      </motion.div>
    </motion.div>
  )
}
