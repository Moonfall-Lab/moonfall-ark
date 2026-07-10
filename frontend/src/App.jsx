import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { useGameData } from './lib/useGameData'
import Scene3D from './components/Scene3D'
import TopBar from './components/TopBar'
import MissionPanel from './components/MissionPanel'
import PlayerBar from './components/PlayerBar'
import EventTimeline from './components/EventTimeline'
import DangerOverlay from './components/DangerOverlay'
import DebugPanel from './components/DebugPanel'
import LoadingScreen from './components/LoadingScreen'

export default function App() {
  const { config, state, events, status } = useGameData()
  const [showDebug, setShowDebug] = useState(false)
  const [showHint, setShowHint] = useState(true)

  // Ctrl+D 调试
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey && (e.key === 'd' || e.key === 'D')) {
        e.preventDefault()
        setShowDebug((s) => !s)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // 操作提示 3 秒后自动淡出
  useEffect(() => {
    const timer = setTimeout(() => setShowHint(false), 3000)
    return () => clearTimeout(timer)
  }, [])

  if (!state || !config) {
    return <LoadingScreen status={status} />
  }

  const isEndgame = state.global?.moon_tier === 'endgame'
  const factions = state.factions || []
  const units = state.units || []
  const unitOf = (fid) => units.find((u) => u.faction === fid)

  // 心率压力贡献
  const stressValues = factions.map((f) => Math.max(0, (f.vars?.heart_rate || 0) - 60))
  const totalStress = stressValues.reduce((s, v) => s + v, 0) || 1
  const stressPctOf = (i) => Math.round((stressValues[i] / totalStress) * 100)

  return (
    <div
      className={`relative w-screen h-screen overflow-hidden flex flex-col ${isEndgame ? 'scanlines-endgame' : ''}`}
      style={{ background: '#090B0C', color: '#E7E1D6', fontFamily: 'IBM Plex Mono, monospace' }}
    >
      {/* 顶部栏 */}
      <TopBar
        rage={state.global?.moon_rage ?? 0}
        tier={state.global?.moon_tier}
        phase={state.phase}
        turn={state.turn}
        status={status}
        factions={factions}
      />

      {/* 主体区域：左任务 | 中地图 | 右事件 */}
      <div className="flex flex-1 min-h-0">
        <div className="w-[220px] flex-shrink-0 p-2">
          <MissionPanel state={state} config={config} />
        </div>

        <div className="flex-1 relative min-w-0">
          <Scene3D config={config} state={state} lastEvent={events[0]} debug={showDebug} />
        </div>

        <div className="w-[260px] flex-shrink-0 p-2">
          <EventTimeline events={events} status={status} rage={state.global?.moon_rage ?? 0} />
        </div>
      </div>

      {/* 底部 4 玩家状态条 */}
      <div className="h-[100px] flex-shrink-0 px-2 pb-2">
        <div className="grid grid-cols-4 gap-2 h-full">
          {factions.map((f, i) => (
            <PlayerBar
              key={f.id}
              faction={f}
              config={config}
              unit={unitOf(f.id)}
              stressPct={stressPctOf(i)}
            />
          ))}
        </div>
      </div>

      {/* 操作提示：3 秒后自动淡出 */}
      <AnimatePresence>
        {showHint && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute bottom-1 left-1/2 -translate-x-1/2 z-20 text-[7px] tracking-widest text-muted/30 pointer-events-none font-mono"
          >
            拖拽旋转 · 滚轮缩放 · 点击聚焦
          </motion.div>
        )}
      </AnimatePresence>

      {/* 终局遮罩 */}
      <AnimatePresence>{isEndgame && <DangerOverlay />}</AnimatePresence>

      {/* 调试面板（Ctrl+D 触发，不展示给观众） */}
      {showDebug && <DebugPanel state={state} status={status} />}
    </div>
  )
}
