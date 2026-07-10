import { useEffect, useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { useGameData } from './lib/useGameData'
import { THEME_STYLE } from './themes'
import MapGrid from './components/MapGrid'
import PlayerPanel from './components/PlayerPanel'
import MoonRageMeter from './components/MoonRageMeter'
import EventLog from './components/EventLog'
import RankBoard from './components/RankBoard'
import DangerOverlay from './components/DangerOverlay'
import DebugPanel from './components/DebugPanel'
import LoadingScreen from './components/LoadingScreen'
import ThemeSwitcher from './components/ThemeSwitcher'

function StatusPill({ status }) {
  const map = {
    live: { c: '#2ecc71', t: '● LIVE' },
    mock: { c: '#f39c12', t: '○ MOCK 演示' },
    connecting: { c: '#00f2ff', t: '… 连接中' },
  }
  const s = map[status] || map.connecting
  return (
    <div className="absolute top-4 left-6 z-40 text-[11px] tracking-widest" style={{ color: s.c }}>
      {s.t}
    </div>
  )
}

export default function App() {
  const { config, state, events, status } = useGameData()
  const [showDebug, setShowDebug] = useState(false)
  const [theme, setTheme] = useState(() => {
    const s = localStorage.getItem('mf_theme')
    return s === 'lunar' || s === 'pixel' ? s : 'lunar'
  })

  useEffect(() => {
    localStorage.setItem('mf_theme', theme)
  }, [theme])

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

  if (!state || !config) {
    return (
      <div data-theme={theme}>
        <LoadingScreen status={status} />
        <ThemeSwitcher theme={theme} onChange={setTheme} />
      </div>
    )
  }

  const ts = THEME_STYLE[theme] || THEME_STYLE.lunar
  const isEndgame = state.global?.moon_tier === 'endgame'
  const factions = state.factions || []
  const unitOf = (fid) => (state.units || []).find((u) => u.faction === fid)

  return (
    <div
      data-theme={theme}
      className={`relative w-screen h-screen overflow-hidden ${ts.scanlines ? 'scanlines' : ''} ${
        isEndgame ? 'animate-pulse-red' : ''
      }`}
      style={{ background: 'var(--bg)', color: 'var(--text)', fontFamily: 'var(--font-body)' }}
    >
      <StatusPill status={status} />

      {/* 中央地图 */}
      <div className="absolute inset-0 flex items-center justify-center">
        <MapGrid
          config={config}
          units={state.units || []}
          zones={state.zones || []}
          tier={state.global?.moon_tier}
          theme={theme}
        />
      </div>

      {/* 四角玩家面板 */}
      <div className="absolute inset-0 p-5 pointer-events-none">
        <div className="flex flex-col justify-between h-full">
          <div className="flex justify-between items-start">
            <PlayerPanel faction={factions[0]} config={config} unit={unitOf(factions[0]?.id)} corner="top-left" />
            <PlayerPanel faction={factions[1]} config={config} unit={unitOf(factions[1]?.id)} corner="top-right" />
          </div>
          <div className="flex justify-between items-end">
            <PlayerPanel faction={factions[2]} config={config} unit={unitOf(factions[2]?.id)} corner="bottom-left" />
            <PlayerPanel faction={factions[3]} config={config} unit={unitOf(factions[3]?.id)} corner="bottom-right" />
          </div>
        </div>
      </div>

      {/* 月球狂暴度 - 顶部居中 */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 w-[34%] max-w-[520px] z-20">
        <MoonRageMeter
          rage={state.global?.moon_rage ?? 0}
          tier={state.global?.moon_tier}
          phase={state.phase}
          turn={state.turn}
        />
      </div>

      {/* 排名结算 - 左侧中部 */}
      <div className="absolute left-6 top-[40%] w-44 z-20 pointer-events-none">
        <RankBoard factions={factions} config={config} />
      </div>

      {/* 事件流 - 右侧中部 */}
      <div className="absolute right-6 top-[36%] w-72 h-[30%] z-20 pointer-events-none">
        <EventLog events={events} />
      </div>

      {/* 终局预警 */}
      <AnimatePresence>{isEndgame && <DangerOverlay />}</AnimatePresence>

      {/* 调试面板 Ctrl+D */}
      {showDebug && <DebugPanel state={state} status={status} />}

      {/* 主题切换 */}
      <ThemeSwitcher theme={theme} onChange={setTheme} />
    </div>
  )
}
