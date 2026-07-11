// 离线演示数据。产出的结构与后端 state.world / state.event 完全一致，
// 便于不连后端时预览大屏，也可作为字段对照。

export const MOCK_CONFIG = {
  game_id: 'moonfall_mvp',
  schema_version: '1.0',
  mode: 'ffa',
  flow: { phases: ['draw', 'command', 'action', 'combat', 'moon', 'resolve'] },
  map: {
    // 真实场地：80cm × 60cm，坐标系原点在左下角
    field: { width_cm: 80, height_cm: 60 },
    grid: [80, 60], // 1cm 一格（路径规划精度）
    zones: [
      // 5 个真实固定目标（来自 rover_fixed_landmarks.md）
      { id: 'energy_w', kind: 'resource', name: '西能源站', center: [1.92, 5.26], radius: 0.58, type: 'energy_station' },
      { id: 'ruins_ne', kind: 'relic', name: '东北遗迹', center: [6.15, 5.11], radius: 0.54, type: 'ruins' },
      { id: 'central_hi', kind: 'resource', name: '中央高能站', center: [3.74, 2.99], radius: 0.58, type: 'high_energy_station' },
      { id: 'ruins_sw', kind: 'relic', name: '西南遗迹', center: [1.27, 1.02], radius: 0.59, type: 'ruins' },
      { id: 'energy_se', kind: 'resource', name: '东南能源站', center: [6.18, 1.39], radius: 0.54, type: 'energy_station' },
      // 动态区域（不预先放置，由后端事件触发产生）
      // { id: 'dust_area', kind: 'hazard', name: '月尘', center: [4.0, 3.0], dynamic: true },
      // { id: 'meteor_area', kind: 'obstacle', name: '陨石', center: [5.0, 4.0], dynamic: true },
      // { id: 'jam_area', kind: 'trap', name: '干扰', center: [3.0, 4.5], dynamic: true },
    ],
  },
  factions: [
    { id: 'pa', name: 'PIONEER A', players: ['p1'] },
    { id: 'pb', name: 'PIONEER B', players: ['p2'] },
  ],
  inputs: { cards: [] },
}

const tierOf = (r) => (r < 25 ? 'sleep' : r < 50 ? 'alert' : r < 80 ? 'anger' : 'endgame')
// 真实场地：80cm × 60cm，坐标单位 = cm / 10（3D 世界单位）
// 原点在左下角，x 范围 0-8，y 范围 0-6
const SHIP = { pa: [0.5, 0.5], pb: [7.5, 0.5] } // 两辆车初始在左下、右下角
const TARGETS = [
  [1.92, 5.26], // energy_w
  [6.15, 5.11], // ruins_ne
  [3.74, 2.99], // central_hi
  [1.27, 1.02], // ruins_sw
  [6.18, 1.39], // energy_se
  [0.5, 0.5],   // 回基地
  [7.5, 0.5],   // 回基地
]
const FIDS = ['pa', 'pb']

export function startMock({ onState, onEvent }) {
  let turn = 1
  let rage = 12
  let nextRank = 1

  const factions = FIDS.map((id) => ({
    id,
    players: MOCK_CONFIG.factions.find((f) => f.id === id).players,
    rank: null,
    vars: {
      fuel: 0, ship_hp: 3, shield: 0, jammed: 0,
      declaring_launch: 0, launched: 0, crashed: 0,
      heart_rate: 78, stress: 0.1,
    },
  }))

  const units = ['r0', 'r1'].map((id, i) => {
    const faction = FIDS[i]
    const [x, y] = SHIP[faction]
    return { id, faction, kind: 'rover', pose: { x, y, theta: 0 }, status: 'idle', carrying: null, _tx: x, _ty: y }
  })

  const zones = MOCK_CONFIG.map.zones.map((z) => ({
    id: z.id, kind: z.kind, active: !z.dynamic, intensity: z.dynamic ? 0 : 1,
  }))

  const snapshot = () => ({
    session_id: 'mock',
    game_id: 'moonfall_mvp',
    schema_version: '1.0',
    phase: MOCK_CONFIG.flow.phases[turn % 6],
    turn,
    global: { moon_rage: Math.round(rage), moon_tier: tierOf(rage) },
    factions: factions.map((f) => ({ id: f.id, players: f.players, rank: f.rank, vars: { ...f.vars } })),
    units: units.map((u) => ({
      id: u.id, faction: u.faction, kind: u.kind,
      pose: { x: u.pose.x, y: u.pose.y, theta: u.pose.theta },
      status: u.status, carrying: u.carrying,
    })),
    zones: zones.map((z) => ({ ...z })),
    rank_order: factions.filter((f) => f.rank).sort((a, b) => a.rank - b.rank).map((f) => f.id),
    winner: null,
  })

  const tick = () => {
    turn += 1
    const avgStress = factions.reduce((s, f) => s + f.vars.stress, 0) / factions.length
    rage = Math.max(0, Math.min(100, rage + (avgStress - 0.4) * 16 + (Math.random() * 10 - 5)))

    factions.forEach((f) => {
      if (f.vars.crashed || f.vars.launched) return
      f.vars.stress = Math.max(0, Math.min(1, f.vars.stress + (Math.random() * 0.2 - 0.09)))
      f.vars.heart_rate = Math.round(78 + f.vars.stress * 70 + (Math.random() * 8 - 4))
      if (Math.random() < 0.22 && f.vars.fuel < 5) f.vars.fuel += 1
      if (f.vars.fuel >= 5 && !f.vars.declaring_launch && !f.vars.launched) {
        f.vars.declaring_launch = 1
        onEvent({ event_type: 'launch_jam', message: `${f.id.toUpperCase()} 宣布点火，月球锁定干扰`, faction: f.id })
      }
      if (f.vars.declaring_launch && !f.vars.launched && Math.random() < 0.4) {
        f.vars.launched = 1
        f.vars.declaring_launch = 0
        f.rank = nextRank++
        onEvent({ event_type: 'ignition_success', message: `${f.id.toUpperCase()} 升空成功，锁定第 ${f.rank} 名`, faction: f.id, data: { rank: f.rank } })
      }
    })

    units.forEach((u) => {
      const f = factions.find((x) => x.id === u.faction)
      if (f.vars.launched || f.vars.crashed) return
      if (Math.abs(u.pose.x - u._tx) < 0.2 && Math.abs(u.pose.y - u._ty) < 0.2) {
        const t = TARGETS[Math.floor(Math.random() * TARGETS.length)]
        u._tx = t[0]
        u._ty = t[1]
        u.carrying = Math.random() < 0.5 ? 'fuel' : null
      }
      u.pose.theta = Math.atan2(u._ty - u.pose.y, u._tx - u.pose.x)
      u.pose.x += (u._tx - u.pose.x) * 0.3
      u.pose.y += (u._ty - u.pose.y) * 0.3
      u.status = u.carrying ? 'return' : 'collect'
    })

    zones.forEach((z) => {
      const cfg = MOCK_CONFIG.map.zones.find((c) => c.id === z.id)
      if (cfg && cfg.dynamic) {
        z.active = rage > 40 && Math.random() < 0.5
        z.intensity = z.active ? Math.min(1, rage / 100) : 0
      }
    })

    if (Math.random() < 0.25) {
      const evs = [
        ['dust_storm', '月尘风暴增强'],
        ['meteor_fall', '陨石坠落，通道受阻'],
        ['central_supply', '中央燃料空投'],
      ]
      const [event_type, message] = evs[Math.floor(Math.random() * evs.length)]
      onEvent({ event_type, message })
    }
    if (tierOf(rage) === 'endgame' && Math.random() < 0.3) {
      onEvent({ event_type: 'enter_boss', message: '终局狂暴：优先干扰点火者' })
    }

    onState(snapshot())
  }

  onState(snapshot())
  const iv = setInterval(tick, 1000)
  return () => clearInterval(iv)
}
