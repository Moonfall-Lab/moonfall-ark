import { useEffect, useState } from 'react'
import { HTTP_BASE, WS_URL, FORCE_MOCK } from '../config'
import { startMock, MOCK_CONFIG } from './mock'

// 统一的数据入口：拉一次 /api/config（静态地图/阵营/卡牌定义），
// 订阅 /ws 实时状态与事件。连不上后端时自动降级到 mock。
export function useGameData() {
  const [config, setConfig] = useState(null)
  const [state, setState] = useState(null)
  const [events, setEvents] = useState([])
  const [status, setStatus] = useState('connecting') // connecting | live | mock

  useEffect(() => {
    let ws
    let stopMock
    let cancelled = false
    let opened = false

    const pushEvent = (ev) =>
      setEvents((prev) => [{ ...ev, _t: Date.now() + Math.random() }, ...prev].slice(0, 12))

    const goMock = () => {
      if (cancelled || stopMock) return
      setStatus('mock')
      setConfig((c) => c || MOCK_CONFIG)
      stopMock = startMock({ onState: setState, onEvent: pushEvent })
    }

    if (FORCE_MOCK) {
      goMock()
      return () => {
        cancelled = true
        if (stopMock) stopMock()
      }
    }

    // 静态配置：真实优先，失败回退 mock 配置
    fetch(`${HTTP_BASE}/api/config`)
      .then((r) => r.json())
      .then((cfg) => !cancelled && setConfig(cfg))
      .catch(() => !cancelled && setConfig((c) => c || MOCK_CONFIG))

    // 实时通道
    try {
      ws = new WebSocket(WS_URL)
      ws.onopen = () => {
        opened = true
        if (!cancelled) setStatus('live')
      }
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data)
          if (msg.topic === 'state.world') setState(msg.payload)
          else if (msg.topic === 'state.event') pushEvent(msg.payload)
        } catch {
          /* 忽略非法消息 */
        }
      }
      ws.onclose = () => {
        if (!opened && !cancelled) goMock()
      }
    } catch {
      goMock()
    }

    // 2.5 秒内没连上，判定后端不可用，降级 mock
    const timer = setTimeout(() => {
      if (!opened && !cancelled) {
        try {
          if (ws) ws.close()
        } catch {
          /* noop */
        }
        goMock()
      }
    }, 2500)

    return () => {
      cancelled = true
      clearTimeout(timer)
      try {
        if (ws) ws.close()
      } catch {
        /* noop */
      }
      if (stopMock) stopMock()
    }
  }, [])

  return { config, state, events, status }
}
