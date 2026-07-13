export default function MissionPanel({ state, config }) {
  const factions = state?.factions || []
  const names = Object.fromEntries((config?.factions || []).map((f) => [f.id, f.name || f.id.toUpperCase()]))

  return (
    <div className="flex h-full flex-col panel">
      <div className="border-b border-white/5 px-3 py-2">
        <span className="text-label">飞船状态 / SHIPS</span>
      </div>
      <div className="flex-1 space-y-3 px-3 py-3">
        {factions.slice(0, 2).map((faction) => {
          const vars = faction.vars || {}
          const hp = vars.hp ?? vars.ship_hp ?? 3
          const fuel = vars.fuel ?? 0
          return (
            <div key={faction.id} className="border-l-2 border-white/15 bg-black/15 px-3 py-2">
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <div>
                  <div className="font-condensed text-lg font-bold text-lunar-white">{faction.id.toUpperCase()}</div>
                  <div className="font-sc text-[9px] text-muted">{names[faction.id]}</div>
                </div>
                {state?.winner === faction.id && (
                  <div className="font-mono text-[9px]" style={{ color: '#E9B44C' }}>WIN</div>
                )}
              </div>

              <div className="space-y-2">
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-mono text-[8px] tracking-[0.15em] text-muted">HP</span>
                    <span className="font-condensed text-sm font-bold tabular-nums" style={{ color: '#F0523D' }}>
                      {hp} / 3
                    </span>
                  </div>
                  <div className="flex gap-1">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div
                        key={i}
                        className="h-3 flex-1"
                        style={{ background: i < hp ? '#F0523D' : 'rgba(255,255,255,0.07)' }}
                      />
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <span className="font-mono text-[8px] tracking-[0.15em] text-muted">燃料块</span>
                    <span className="font-condensed text-sm font-bold tabular-nums" style={{ color: '#E9B44C' }}>
                      {fuel} / 5
                    </span>
                  </div>
                  <div className="flex gap-1">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <div
                        key={i}
                        className="h-3 flex-1"
                        style={{ background: i < fuel ? '#E9B44C' : 'rgba(255,255,255,0.07)' }}
                      />
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
