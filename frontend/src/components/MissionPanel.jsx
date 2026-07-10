// 左侧任务面板：按阶段切换内容
// 正常阶段：任务进度 + 关键贡献
// 终局阶段：撤离状态
// 结算阶段：最终结果

export default function MissionPanel({ state, config }) {
  const factions = state?.factions || []
  const units = state?.units || []
  const tier = state?.global?.moon_tier || 'sleep'

  // 燃料总量（所有阵营燃料之和，目标 20）
  const totalFuel = factions.reduce((s, f) => s + (f.vars?.fuel || 0), 0)
  const fuelTarget = 20

  // 方舟修复度（所有阵营 ship_hp 之和 / 满血）
  const totalHp = factions.reduce((s, f) => s + (f.vars?.ship_hp || 0), 0)
  const maxHp = factions.length * 3
  const repairPct = Math.round((totalHp / maxHp) * 100)

  // 幸存机器人
  const aliveUnits = units.filter((u) => u.status !== 'destroyed').length
  const totalUnits = units.length || 4

  // 升空数
  const launchedCount = factions.filter((f) => f.vars?.launched).length
  const notLaunched = factions.filter((f) => !f.vars?.launched && !f.vars?.crashed)
  const crashedCount = factions.filter((f) => f.vars?.crashed).length

  // 关键贡献者：燃料最多
  const topContributor = [...factions].sort((a, b) => (b.vars?.fuel || 0) - (a.vars?.fuel || 0))[0]

  // 阶段判断：所有阵营升空或坠毁后才算结算
  // 同时要求至少有 1 人升空（避免开局全部未动就算结算）
  const isEndgame = tier === 'endgame'
  const allDone = factions.length > 0 && factions.every((f) => f.vars?.launched || f.vars?.crashed)
  const hasLaunched = launchedCount > 0
  const isResolved = allDone && hasLaunched

  // ========== 正常阶段 ==========
  function renderNormal() {
    const items = [
      { label: '燃料收集', code: 'FUEL', value: `${totalFuel} / ${fuelTarget}`, pct: Math.min(100, (totalFuel / fuelTarget) * 100), color: '#63C7C4' },
      { label: '方舟修复', code: 'REPAIR', value: `${repairPct}%`, pct: repairPct, color: '#7FB069' },
      { label: '幸存机器人', code: 'ROVERS', value: `${aliveUnits} / ${totalUnits}`, pct: (aliveUnits / totalUnits) * 100, color: '#E7E1D6' },
      { label: '已升空', code: 'LAUNCH', value: `${launchedCount} / ${factions.length}`, pct: (launchedCount / factions.length) * 100, color: '#E9B44C' },
    ]

    // 因果总结
    const stressValues = factions.map((f) => Math.max(0, (f.vars?.heart_rate || 0) - 60))
    const totalStress = stressValues.reduce((s, v) => s + v, 0) || 1
    const topStressIdx = stressValues.indexOf(Math.max(...stressValues))
    const topStressFaction = factions[topStressIdx]
    const topStressPct = Math.round((stressValues[topStressIdx] / totalStress) * 100)

    return (
      <>
        <div className="flex-1 px-3 py-2 space-y-3">
          {items.map((it) => (
            <div key={it.code}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-[8px] font-mono tracking-[0.15em]" style={{ color: it.color }}>{it.code}</span>
                  <span className="font-sc text-[10px] font-medium text-muted-text">{it.label}</span>
                </div>
                <span className="font-condensed text-sm font-bold tabular-nums" style={{ color: it.color }}>
                  {it.value}
                </span>
              </div>
              <div className="h-[3px] bg-white/5 overflow-hidden">
                <div className="h-full transition-all duration-500" style={{ width: `${it.pct}%`, background: it.color }} />
              </div>
            </div>
          ))}
        </div>

        {/* 关键贡献 */}
        <div className="px-3 py-2 border-t border-white/5">
          <div className="text-[8px] font-mono text-muted tracking-[0.15em] mb-1">关键贡献 / TOP</div>
          {topContributor && topContributor.vars?.fuel > 0 ? (
            <div className="flex items-center gap-2">
              <span className="font-condensed text-base font-bold text-lunar-white">
                {topContributor.id.toUpperCase()}
              </span>
              <span className="text-[9px] text-muted font-mono">
                燃料 {topContributor.vars.fuel} · HR {topContributor.vars.heart_rate || '—'}
              </span>
            </div>
          ) : (
            <span className="text-[9px] text-muted font-sc">尚无数据</span>
          )}
        </div>

        {/* 因果总结 */}
        {topStressFaction && topStressPct > 0 && (
          <div className="px-3 py-2 border-t border-white/5">
            <div className="text-[8px] font-mono text-muted tracking-[0.15em] mb-1.5">因果总结 / CAUSAL</div>
            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-sc text-[9px] text-muted-text">最高压力玩家</span>
                <span className="font-condensed text-xs font-bold" style={{ color: '#F0523D' }}>
                  {topStressFaction.id.toUpperCase()}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="font-sc text-[9px] text-muted-text">狂暴贡献</span>
                <span className="font-condensed text-xs font-bold tabular-nums" style={{ color: '#F0523D' }}>
                  {topStressPct}%
                </span>
              </div>
            </div>
          </div>
        )}
      </>
    )
  }

  // ========== 终局阶段 ==========
  function renderEndgame() {
    return (
      <div className="flex-1 px-3 py-2 space-y-3">
        <div className="text-[8px] font-mono text-muted tracking-[0.15em]">FINAL EXTRACTION</div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-sc text-[10px] font-medium text-muted-text">已升空</span>
            <span className="font-condensed text-lg font-bold tabular-nums" style={{ color: '#7FB069' }}>
              {launchedCount} / {factions.length}
            </span>
          </div>

          {notLaunched.length > 0 && (
            <div>
              <span className="font-sc text-[10px] font-medium text-muted-text">未撤离</span>
              <div className="flex gap-1.5 mt-1">
                {notLaunched.map((f) => (
                  <span key={f.id} className="font-condensed text-sm font-bold" style={{ color: '#F0523D' }}>
                    {f.id.toUpperCase()}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between">
            <span className="font-sc text-[10px] font-medium text-muted-text">已坠毁</span>
            <span className="font-condensed text-sm font-bold tabular-nums" style={{ color: '#8E9497' }}>
              {crashedCount}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="font-sc text-[10px] font-medium text-muted-text">方舟完整度</span>
            <span className="font-condensed text-sm font-bold tabular-nums" style={{ color: repairPct > 50 ? '#7FB069' : '#F0523D' }}>
              {repairPct}%
            </span>
          </div>
        </div>

        <div className="pt-2 border-t border-white/5">
          <div className="text-[8px] font-mono text-muted tracking-[0.15em] mb-1">威胁状态</div>
          <div className="font-sc text-[10px]" style={{ color: '#F0523D' }}>
            机械臂已解除攻击限制
          </div>
        </div>
      </div>
    )
  }

  // ========== 结算阶段 ==========
  function renderResult() {
    const fuelEff = Math.round((totalFuel / (state?.turn || 1)) * 10)
    return (
      <div className="flex-1 px-3 py-2 space-y-3">
        <div className="text-[8px] font-mono text-muted tracking-[0.15em]">MISSION RESULT</div>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-sc text-[10px] font-medium text-muted-text">幸存者</span>
            <span className="font-condensed text-lg font-bold tabular-nums" style={{ color: '#7FB069' }}>
              {aliveUnits} / {totalUnits}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-sc text-[10px] font-medium text-muted-text">成功升空</span>
            <span className="font-condensed text-lg font-bold tabular-nums" style={{ color: '#E9B44C' }}>
              {launchedCount} / {factions.length}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-sc text-[10px] font-medium text-muted-text">燃料效率</span>
            <span className="font-condensed text-sm font-bold tabular-nums text-lunar-white">
              {fuelEff}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="font-sc text-[10px] font-medium text-muted-text">方舟损伤</span>
            <span className="font-condensed text-sm font-bold tabular-nums" style={{ color: '#F0523D' }}>
              {100 - repairPct}%
            </span>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full panel">
      <div className="px-3 py-2 border-b border-white/5">
        <span className="text-label">
          {isResolved ? '任务结算 / RESULT' : isEndgame ? '终局撤离 / EXTRACTION' : '任务状态 / MISSION STATUS'}
        </span>
      </div>
      {isResolved ? renderResult() : isEndgame ? renderEndgame() : renderNormal()}
    </div>
  )
}
