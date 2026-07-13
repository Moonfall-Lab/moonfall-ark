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
  const units = state?.units || []
  const zones = state?.zones || []
  const zoneConfigById = Object.fromEntries((config?.map?.zones || []).map((z) => [z.id, z]))
  const stockZones = zones
    .map((z) => ({ ...zoneConfigById[z.id], ...z }))
    .filter((z) => z.kind === 'resource' || z.kind === 'relic')

  return (
    <div className="absolute inset-0">
      <div ref={holder} className="absolute inset-0" />
      <div className="absolute left-3 top-3 z-20 w-[260px] border border-white/10 bg-black/70 p-2 font-mono text-[9px] text-lunar-white shadow-lg backdrop-blur">
        <div className="mb-1 text-[8px] tracking-[0.18em] text-muted">ROVER TELEMETRY</div>
        <div className="space-y-1">
          {units.map((unit) => {
            const pose = unit.pose || {}
            const target = unit.target
            return (
              <div key={unit.id} className="border-l-2 border-white/20 pl-2">
                <div className="flex items-center justify-between">
                  <span className="font-bold">{unit.id.toUpperCase()}</span>
                  <span className="text-muted">{unit.status || 'idle'}</span>
                </div>
                <div className="text-muted">
                  POS {Number(pose.x || 0).toFixed(2)}, {Number(pose.y || 0).toFixed(2)}
                </div>
                <div style={{ color: target ? '#E9B44C' : 'var(--muted-text)' }}>
                  TGT {target ? `${target.name || target.landmark_id} · ${Number(target.x || 0).toFixed(2)}, ${Number(target.y || 0).toFixed(2)}` : 'none'}
                </div>
              </div>
            )
          })}
        </div>
      </div>
      <div className="absolute right-3 top-3 z-20 w-[230px] border border-white/10 bg-black/70 p-2 font-mono text-[9px] text-lunar-white shadow-lg backdrop-blur">
        <div className="mb-1 text-[8px] tracking-[0.18em] text-muted">FIELD STOCK</div>
        <div className="space-y-1">
          {stockZones.map((zone) => (
            <div key={zone.id} className="flex items-center justify-between gap-2">
              <span className="truncate">{zone.name || zone.id}</span>
              <span style={{ color: zone.kind === 'relic' ? '#B08FC7' : '#E9B44C' }}>
                {zone.kind === 'relic' ? `RELIC ${zone.relic_cards ?? 0}` : `FUEL ${zone.fuel_blocks ?? 0}`}
              </span>
            </div>
          ))}
        </div>
      </div>
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
