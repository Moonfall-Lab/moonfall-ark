import { motion } from 'framer-motion'

// 克制的终局遮罩：屏幕边缘暗角 + 顶部细条警告
// 不再使用巨大的 ENDGAME 文字
export default function DangerOverlay() {
  return (
    <>
      {/* 屏幕边缘暗红色暗角 */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="absolute inset-0 pointer-events-none z-40"
        style={{
          boxShadow: 'inset 0 0 200px rgba(240, 82, 61, 0.15)',
        }}
      />

      {/* 顶部细条警告 */}
      <motion.div
        initial={{ y: -30, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: -30, opacity: 0 }}
        className="absolute top-[60px] left-1/2 -translate-x-1/2 z-40 pointer-events-none"
      >
        <div className="flex items-center px-4 py-1 danger-bar">
          <span className="text-[10px] font-mono font-semibold tracking-wider" style={{ color: '#FF2F2F' }}>
            ⚠ ENDGAME
          </span>
        </div>
      </motion.div>
    </>
  )
}
