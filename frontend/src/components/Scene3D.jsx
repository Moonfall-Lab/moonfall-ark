import { useEffect, useRef, useState } from 'react'
import MoonScene from '../three/MoonScene'

// three.js 场景的 React 壳：负责生命周期与数据桥接
export default function Scene3D({ config, state, lastEvent, debug = false }) {
  const holder = useRef(null)
  const sceneRef = useRef(null)
  const [progress, setProgress] = useState(0)
  const [ready, setReady] = useState(false)
  const [armAlert, setArmAlert] = useState(null)

  useEffect(() => {
    const scene = new MoonScene({
      onProgress: setProgress,
      onReady: () => setReady(true),
    })
    sceneRef.current = scene
    scene.mount(holder.current)
    return () => {
      scene.dispose()
      sceneRef.current = null
    }
  }, [])

  useEffect(() => {
    if (config && sceneRef.current) sceneRef.current.setConfig(config)
  }, [config])

  useEffect(() => {
    if (state && sceneRef.current) sceneRef.current.updateState(state)
  }, [state])

  useEffect(() => {
    if (!lastEvent || !sceneRef.current) return
    sceneRef.current.pushEvent(lastEvent)

    const type = lastEvent.event_type || ''
    if (!/arm|meteor|jam|boss|attack|strike/i.test(type)) return
    const target = (lastEvent.faction || lastEvent.zone || 'ARK').toUpperCase()
    const expiresAt = performance.now() + 3200
    setArmAlert({ target, remaining: 3.2 })
    const timer = window.setInterval(() => {
      const remaining = Math.max(0, (expiresAt - performance.now()) / 1000)
      setArmAlert(remaining > 0 ? { target, remaining } : null)
      if (remaining <= 0) window.clearInterval(timer)
    }, 100)
    return () => window.clearInterval(timer)
  }, [lastEvent])

  const launchShip = (fid) => sceneRef.current?.launchShip(fid)
  const factions = config?.factions || []

  return (
    <div className="absolute inset-0">
      <div ref={holder} className="absolute inset-0" />
      {armAlert && (
        <div className="absolute top-3 left-1/2 z-20 -translate-x-1/2 border border-red-500/40 bg-black/80 px-5 py-2 text-center shadow-lg">
          <div className="text-[10px] tracking-[0.28em] text-red-400">⚠ ARM STRIKE</div>
          <div className="mt-1 font-mono text-[11px] text-white">
            TARGET {armAlert.target} · {armAlert.remaining.toFixed(1)} SEC
          </div>
        </div>
      )}
      {ready && debug && (
        <div className="absolute top-3 left-3 z-20 flex items-center gap-1.5 rounded border border-white/10 bg-black/70 p-2">
          <span className="mr-1 text-[9px] tracking-widest text-muted">LAUNCH TEST</span>
          {factions.slice(0, 4).map((faction, index) => (
            <button
              key={faction.id}
              type="button"
              className="debug-btn"
              onClick={() => launchShip(faction.id)}
            >
              起飞 {String.fromCharCode(65 + index)}
            </button>
          ))}
          <button type="button" className="debug-btn" onClick={() => sceneRef.current?.resetShips()}>
            复位
          </button>
        </div>
      )}
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10" style={{ background: 'rgba(9, 11, 12, 0.7)' }}>
          <div className="text-center">
            <div className="font-condensed text-sm tracking-[0.3em] text-muted-text">
              INITIALIZING TERRAIN
            </div>
            <div className="mt-2 w-48 h-[2px] mx-auto bg-white/5 overflow-hidden">
              <div
                className="h-full transition-all duration-300"
                style={{ width: `${progress}%`, background: '#63C7C4' }}
              />
            </div>
            <div className="mt-1 text-[9px] text-muted/50 font-mono">{progress}%</div>
          </div>
        </div>
      )}
    </div>
  )
}
