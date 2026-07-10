import { useEffect, useRef, useState } from 'react'
import MoonScene from '../three/MoonScene'

// three.js 场景的 React 壳：负责生命周期与数据桥接
export default function Scene3D({ config, state, lastEvent }) {
  const holder = useRef(null)
  const sceneRef = useRef(null)
  const [progress, setProgress] = useState(0)
  const [ready, setReady] = useState(false)

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
    if (lastEvent && sceneRef.current) sceneRef.current.pushEvent(lastEvent)
  }, [lastEvent])

  return (
    <div className="absolute inset-0">
      <div ref={holder} className="absolute inset-0" />
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
          <div className="text-center">
            <div className="title-font tracking-[0.4em] text-lg" style={{ color: 'var(--accent)' }}>
              LOADING LUNAR ASSETS
            </div>
            <div className="mt-3 w-64 h-1 mx-auto bg-white/10 overflow-hidden rounded">
              <div
                className="h-full transition-all duration-300"
                style={{ width: `${progress}%`, background: 'var(--accent)', boxShadow: '0 0 12px var(--accent)' }}
              />
            </div>
            <div className="mt-2 text-xs muted">{progress}%</div>
          </div>
        </div>
      )}
    </div>
  )
}
