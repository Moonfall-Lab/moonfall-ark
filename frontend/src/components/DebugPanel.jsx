import { HTTP_BASE } from '../config'

// 导播调试台。按钮通过 REST 触发后端调试接口，仅在连真后端(live)时生效。
const post = (path, body) =>
  fetch(`${HTTP_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).catch(() => {})

export default function DebugPanel({ state, status }) {
  const live = status === 'live'
  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-50 w-[600px] bg-black/85 border border-glacier/40 rounded-lg p-4 text-xs">
      <div className="flex items-center justify-between mb-3">
        <span className="text-glacier font-bold tracking-widest">DEBUG · Ctrl+D</span>
        <span className="text-white/40">{live ? '● LIVE' : '○ MOCK（按钮仅在连后端时生效）'}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          className="debug-btn"
          onClick={() => post('/api/debug/set_var', { scope: 'global', id: '', var: 'moon_rage', value: 100 })}
        >
          Force Rage 100
        </button>
        <button className="debug-btn" onClick={() => post('/api/debug/trigger_event', { event_id: 'meteor_fall' })}>
          Trigger Meteor
        </button>
        <button className="debug-btn" onClick={() => post('/api/debug/trigger_event', { event_id: 'dust_storm' })}>
          Trigger Dust
        </button>
        <button
          className="debug-btn"
          onClick={() => post('/api/debug/set_var', { scope: 'faction', id: 'pa', var: 'fuel', value: 5 })}
        >
          PA fuel = 5
        </button>
        <button className="debug-btn" onClick={() => post('/api/control/reset', {})}>
          Reset
        </button>
      </div>
      <pre className="mt-3 max-h-40 overflow-auto text-[10px] text-white/50">
        {JSON.stringify({ phase: state?.phase, turn: state?.turn, global: state?.global }, null, 2)}
      </pre>
    </div>
  )
}
