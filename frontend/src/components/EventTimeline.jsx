import { AnimatePresence, motion } from 'framer-motion'
import { factionColor } from '../lib/factions'

const EVENT_META = {
  dust_storm: { title: '月尘风暴等级上升', code: 'SEV-03', severity: 3, color: '#D84A3A', sector: 'C2—D3', duration: '00:18' },
  meteor_fall: { title: '陨石冲击', code: 'SEV-04', severity: 4, color: '#D84A3A', sector: 'B2 / C4', duration: '等待清理' },
  enter_boss: { title: '月球意图强度超限', code: 'SEV-05', severity: 5, color: '#FF2F2F', sector: '全域', duration: '持续' },
  launch_jam: { title: '发射通道受干扰', code: 'SEV-02', severity: 2, color: '#D9A83E', sector: '泊位区', duration: '00:08' },
  ignition_success: { title: '升空序列完成', code: 'REC-01', severity: 0, color: '#7FB069', sector: '撤离走廊' },
  ship_crashed: { title: '舰体结构失效', code: 'SEV-04', severity: 4, color: '#D84A3A', sector: '玩家泊位' },
  central_supply: { title: '中央燃料投放完成', code: 'LOG-02', severity: 0, color: '#69C9C7', sector: 'ARK DOCK' },
  betrayal: { title: '协作协议异常', code: 'SEV-02', severity: 2, color: '#D9A83E', sector: '战术网络' },
  rank_locked: { title: '撤离序位已锁定', code: 'REC-02', severity: 0, color: '#AEB5B5', sector: '任务控制' },
  prayer_response: { title: '月面响应已确认', code: 'LOG-03', severity: 1, color: '#7FB069', sector: '未知' },
  voice_command: { title: '语音指令已解析', code: 'LOG-01', severity: 0, color: '#69C9C7', sector: 'AGENT NET' },
  card_input: { title: '战术输入已接收', code: 'LOG-01', severity: 0, color: '#AEB5B5', sector: 'AGENT NET' },
}

const FALLBACK_META = { title: '未分类遥测记录', code: 'LOG-00', severity: 0, color: '#8E9497', sector: '未标记' }

function formatTime(t) {
  if (!t) return '--:--:--'
  const d = new Date(t)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function mergeEvents(events) {
  const merged = []
  for (const ev of events || []) {
    if (!ev?._t) continue
    const existing = merged.find((item) => item.event_type === ev.event_type && item.firstTime - ev._t <= 30000)
    if (existing) {
      existing.count += 1
      existing.lastTime = ev._t
      existing.lastEv = ev
    } else {
      merged.push({ ...ev, count: 1, firstTime: ev._t, lastTime: ev._t, lastEv: ev })
    }
  }
  return merged
}

function affectedLabel(ev) {
  const affected = ev.data?.affected || ev.faction
  if (Array.isArray(affected)) return affected.map((id) => String(id).toUpperCase()).join(' / ')
  if (affected) return String(affected).toUpperCase()
  if (ev.event_type === 'dust_storm' || ev.event_type === 'meteor_fall') return 'ARK / FIELD'
  return 'SYSTEM'
}

function PlayerTag({ id }) {
  const key = id.toLowerCase()
  return (
    <span className="inline-flex items-center gap-1 font-mono text-[7px] text-muted">
      <i className="h-1.5 w-1.5" style={{ background: factionColor(key) }} />
      {id}
    </span>
  )
}

export default function EventTimeline({ events, status = 'mock', rage = 0 }) {
  const merged = mergeEvents(events)
  const active = merged.filter((ev) => (EVENT_META[ev.event_type] || FALLBACK_META).severity >= 2).slice(0, 1)
  const activeThreat = active.reduce((max, ev) => Math.max(max, (EVENT_META[ev.event_type] || FALLBACK_META).severity), 0)
  const threat = Math.max(activeThreat, Math.max(0, Math.min(5, Math.ceil(rage / 20))))
  const history = merged.filter((ev) => !active.includes(ev))

  return (
    <div className="flex h-full flex-col panel">
      <header className="border-b border-white/[0.06] px-3 py-2.5">
        <div className="flex items-start justify-between">
          <div>
            <div className="font-mono text-[9px] tracking-[0.18em] text-[#AEB5B5]">LUNAR TELEMETRY</div>
            <div className="mt-0.5 font-sc text-[10px] text-muted">月面遥测记录器</div>
          </div>
          <span className="font-mono text-[8px] text-muted/60">REC {String(merged.length).padStart(3, '0')}</span>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-x-3 font-mono text-[7px] tracking-wider text-muted/60">
          <span>LINK <b className={status === 'live' ? 'text-[#69C9C7]' : 'text-[#D9A83E]'}>{status === 'live' ? 'ONLINE' : 'LOCAL'}</b></span>
          <span>THREAT <b className={threat >= 4 ? 'text-[#D84A3A]' : 'text-[#AEB5B5]'}>LEVEL {String(threat).padStart(2, '0')}</b></span>
        </div>
      </header>

      {active.map((ev) => {
        const meta = EVENT_META[ev.event_type] || FALLBACK_META
        return (
          <section key={`active-${ev.event_type}`} className="border-b border-white/[0.06] px-3 py-2.5">
            <div className="mb-2 font-mono text-[7px] tracking-[0.2em] text-[#D84A3A]">ACTIVE CONDITION</div>
            <div className="border-l-2 pl-2.5" style={{ borderColor: meta.color }}>
              <div className="flex items-center justify-between font-mono text-[7px]">
                <span style={{ color: meta.color }}>{meta.code}</span>
                <span className="text-muted/50">{meta.duration || '持续监测'}</span>
              </div>
              <div className="mt-1 font-sc text-[11px] font-semibold text-[#E7E1D6]">{meta.title}{ev.count > 1 ? ` ×${ev.count}` : ''}</div>
              <div className="mt-1.5 grid grid-cols-[52px_1fr] gap-y-1 font-mono text-[7px] text-muted/60">
                <span>SECTOR</span><span className="text-muted">{ev.zone?.toUpperCase?.() || meta.sector}</span>
                <span>AFFECTED</span><PlayerTag id={affectedLabel(ev)} />
              </div>
            </div>
          </section>
        )
      })}

      <div className="flex-1 overflow-y-auto px-3 py-2">
        <div className="mb-1.5 font-mono text-[7px] tracking-[0.18em] text-muted/40">EVENT HISTORY</div>
        <AnimatePresence initial={false}>
          {history.length === 0 && <div className="py-6 text-center font-mono text-[8px] text-muted/40">AWAITING TELEMETRY</div>}
          {history.map((ev, index) => {
            const meta = EVENT_META[ev.event_type] || FALLBACK_META
            const compact = index >= 4
            const affected = affectedLabel(ev)
            return (
              <motion.div
                key={`${ev.event_type}-${ev.firstTime}`}
                layout
                initial={{ opacity: 0, x: 10 }}
                animate={{ opacity: Math.max(0.42, 1 - index * 0.08), x: 0 }}
                exit={{ opacity: 0, height: 0 }}
                className={`relative border-b border-white/[0.035] py-2 pl-3 ${compact ? 'py-1.5' : ''}`}
              >
                <i className="absolute bottom-2 left-0 top-2 w-[2px]" style={{ background: meta.severity >= 2 ? meta.color : 'rgba(174,181,181,0.18)' }} />
                <div className="flex items-center gap-2 font-mono text-[7px] tabular-nums">
                  <span className="text-muted/45">{formatTime(ev.firstTime)}</span>
                  <span style={{ color: meta.severity >= 2 ? meta.color : '#8E9497' }}>{meta.code}</span>
                  {ev.count > 1 && <span className="text-muted/60">×{ev.count}</span>}
                </div>
                <div className={`mt-1 font-sc text-[10px] ${index === 0 ? 'text-[#E7E1D6]' : 'text-muted'}`}>{meta.title}</div>
                {!compact && (
                  <div className="mt-1 flex items-center justify-between font-mono text-[7px] text-muted/45">
                    <span>{ev.zone?.toUpperCase?.() || meta.sector}</span>
                    {affected !== 'SYSTEM' && <PlayerTag id={affected} />}
                  </div>
                )}
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </div>
  )
}
