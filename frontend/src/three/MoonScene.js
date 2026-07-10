// MoonFall 3D 实时场景引擎（three.js）
// 职责：月面环境 / 模型摆放 / 小车实时移动 / 事件特效 / 月怒氛围。
// React 侧只需调用 mount / setConfig / updateState / pushEvent / dispose。
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { FACTION_COLORS } from '../lib/factions'

const GRID = 12 // 12x12 棋盘
const MODELS = {
  ship_a: 'ship1',
  ship_b: 'ship2',
  ship_c: 'ship3',
  ship_d: 'ship4',
  resource: 'resource_station',
  central: 'fuel_station',
  relic_top: 'altar1',
  relic_bottom: 'altar2',
  hazard: 'dust_device',
  obstacle: 'meteor',
}
const KIND_COLOR = {
  base: 0x00f2ff,
  resource: 0xa29bfe,
  relic: 0x2ecc71,
  hazard: 0xbbbbbb,
  obstacle: 0xff4d4d,
  trap: 0xf39c12,
}
const RAGE_ENV = {
  sleep: { fog: 0x0a0e16, hemi: 0x8899bb, sun: 0xfff4e0, sunI: 2.2, red: 0.0 },
  alert: { fog: 0x101020, hemi: 0x9988aa, sun: 0xffe8c8, sunI: 2.4, red: 0.15 },
  anger: { fog: 0x1a0d10, hemi: 0xaa7788, sun: 0xffc9a0, sunI: 2.6, red: 0.5 },
  endgame: { fog: 0x220a0a, hemi: 0xcc6666, sun: 0xff9070, sunI: 3.0, red: 1.0 },
}

const gx2w = (gx) => gx - GRID / 2 // 网格坐标 -> 世界坐标
const gy2w = (gy) => gy - GRID / 2

function glowSpriteTexture(inner = 'rgba(255,255,255,1)', outer = 'rgba(255,255,255,0)') {
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const g = c.getContext('2d')
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64)
  grad.addColorStop(0, inner)
  grad.addColorStop(0.35, inner.replace(/,1\)/, ',0.55)'))
  grad.addColorStop(1, outer)
  g.fillStyle = grad
  g.fillRect(0, 0, 128, 128)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

function labelSprite(text, color = '#e8f0ff') {
  const c = document.createElement('canvas')
  const g = c.getContext('2d')
  const font = '600 42px "JetBrains Mono", monospace'
  g.font = font
  const w = Math.ceil(g.measureText(text).width) + 36
  c.width = w
  c.height = 72
  const g2 = c.getContext('2d')
  g2.font = font
  g2.fillStyle = 'rgba(5,8,14,0.35)'
  g2.beginPath()
  g2.roundRect(0, 6, w, 60, 10)
  g2.fill()
  g2.fillStyle = color
  g2.textBaseline = 'middle'
  g2.fillText(text, 18, 38)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  const m = new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false })
  const s = new THREE.Sprite(m)
  s.scale.set(w / 90, 0.8, 1)
  return s
}

export default class MoonScene {
  constructor({ onProgress, onReady } = {}) {
    this.onProgress = onProgress || (() => {})
    this.onReady = onReady || (() => {})
    this.models = {} // name -> gltf scene 模板
    this.zoneNodes = {} // zone id -> group
    this.zoneRings = {} // zone id -> ring mesh
    this.rovers = {} // unit id -> rover group
    this.ships = {} // faction id -> ship node（发射动画用）
    this.fx = [] // 活跃特效
    this.prevVars = {} // faction id -> vars（diff 检测发射/坠毁）
    this.rageTier = 'sleep'
    this.rage = 0
    this.shake = 0
    this.clock = new THREE.Clock()
    this._config = null
    this._pendingState = null
    this._ready = false
    this._disposed = false
  }

  mount(container) {
    this.container = container
    const w = container.clientWidth
    const h = container.clientHeight

    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' })
    this.renderer.setSize(w, h)
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    container.appendChild(this.renderer.domElement)

    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0x05070c)
    this.scene.fog = new THREE.FogExp2(0x0a0e16, 0.014)
    // 关键：PBR 金属材质必须有环境贴图，否则反射为纯黑
    // 用 envMapIntensity 在材质级别加强环境光
    const pmrem = new THREE.PMREMGenerator(this.renderer)
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    pmrem.dispose()

    this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 300)
    this.camera.position.set(13, 11, 13)

    this.renderer.domElement.style.touchAction = 'none' // 触屏/触控板双指捏合缩放交给 OrbitControls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.target.set(0, 0.6, 0)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.06
    this.controls.autoRotate = true
    this.controls.autoRotateSpeed = 0.5
    this.controls.minDistance = 5
    this.controls.maxDistance = 40
    this.controls.maxPolarAngle = Math.PI * 0.47
    this.controls.addEventListener('start', () => (this.controls.autoRotate = false))

    // 泛光后期
    this.composer = new EffectComposer(this.renderer)
    this.composer.addPass(new RenderPass(this.scene, this.camera))
    this.bloom = new UnrealBloomPass(new THREE.Vector2(w, h), 0.75, 0.55, 0.82)
    this.composer.addPass(this.bloom)
    this.composer.addPass(new OutputPass())

    this._buildLights()
    this._buildTerrain()
    this._buildSky()
    this._buildJammer()
    this._loadModels()

    this._onResize = () => {
      const W = container.clientWidth
      const H = container.clientHeight
      this.camera.aspect = W / H
      this.camera.updateProjectionMatrix()
      this.renderer.setSize(W, H)
      this.composer.setSize(W, H)
    }
    window.addEventListener('resize', this._onResize)

    // 点击聚焦：射线命中区域 -> 相机目标平滑移动
    this._raycaster = new THREE.Raycaster()
    this._focusTo = null
    this._onClick = (e) => {
      const r = this.renderer.domElement.getBoundingClientRect()
      const p = new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1)
      this._raycaster.setFromCamera(p, this.camera)
      const targets = Object.values(this.zoneNodes)
      const hits = this._raycaster.intersectObjects(targets, true)
      if (hits.length) {
        let n = hits[0].object
        while (n.parent && !n.userData.zoneId) n = n.parent
        this._focusTo = n.position.clone().setY(0.8)
      }
    }
    this.renderer.domElement.addEventListener('click', this._onClick)

    this.renderer.setAnimationLoop(() => this._tick())
  }

  // ---------- 环境 ----------
  _buildLights() {
    this.hemi = new THREE.HemisphereLight(0x8899bb, 0x0c0a08, 0.7)
    this.scene.add(this.hemi)
    this.sun = new THREE.DirectionalLight(0xfff4e0, 2.2)
    this.sun.position.set(18, 26, 10)
    this.scene.add(this.sun)
    // 月怒之光：陨石区下方的红色脉冲灯
    this.rageLight = new THREE.PointLight(0xff3020, 0, 30)
    this.rageLight.position.set(0, 4, 0)
    this.scene.add(this.rageLight)
  }

  _buildTerrain() {
    const loader = new THREE.TextureLoader()
    const tex = loader.load('/assets/lunar/background.avif')
    tex.colorSpace = THREE.SRGBColorSpace
    tex.wrapS = tex.wrapT = THREE.MirroredRepeatWrapping
    tex.repeat.set(2.2, 2.2)
    tex.anisotropy = 8

    // 带起伏的月面：棋盘区域保持平整，四周隆起随机丘陵
    const size = 130
    const seg = 160
    const geo = new THREE.PlaneGeometry(size, size, seg, seg)
    const pos = geo.attributes.position
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i)
      const y = pos.getY(i)
      const d = Math.max(Math.abs(x), Math.abs(y))
      const edge = THREE.MathUtils.smoothstep(d, GRID / 2 + 1.5, size / 2)
      const n =
        Math.sin(x * 0.35) * Math.cos(y * 0.28) * 1.6 +
        Math.sin(x * 0.9 + 3.1) * Math.cos(y * 0.7 + 1.7) * 0.7 +
        Math.sin(x * 2.3 + 7.7) * Math.cos(y * 1.9 + 4.2) * 0.25
      pos.setZ(i, edge * (Math.abs(n) * 2.2 + n * 0.6))
    }
    geo.computeVertexNormals()
    const mat = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.96, metalness: 0.02, side: THREE.DoubleSide, envMapIntensity: 0.6 })
    this.ground = new THREE.Mesh(geo, mat)
    this.ground.rotation.x = -Math.PI / 2
    this.scene.add(this.ground)

    // 棋盘霓虹网格
    const gpts = []
    for (let i = 0; i <= GRID; i++) {
      const v = i - GRID / 2
      gpts.push(-GRID / 2, 0, v, GRID / 2, 0, v)
      gpts.push(v, 0, -GRID / 2, v, 0, GRID / 2)
    }
    const ggeo = new THREE.BufferGeometry()
    ggeo.setAttribute('position', new THREE.Float32BufferAttribute(gpts, 3))
    this.gridLines = new THREE.LineSegments(
      ggeo,
      new THREE.LineBasicMaterial({ color: 0x00f2ff, transparent: true, opacity: 0.22, blending: THREE.AdditiveBlending, depthWrite: false })
    )
    this.gridLines.position.y = 0.02
    this.scene.add(this.gridLines)

    // 棋盘外框（亮一档，吃泛光）
    // 方形环：4 段 RingGeometry 的“半径”是角点距离，边距 = r·cos45°
    const br = (GRID / 2 + 0.18) / Math.cos(Math.PI / 4)
    const border = new THREE.Mesh(
      new THREE.RingGeometry(br, br + 0.26, 4, 1, Math.PI / 4),
      new THREE.MeshBasicMaterial({ color: 0x00f2ff, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false })
    )
    border.rotation.x = -Math.PI / 2
    border.position.y = 0.03
    this.scene.add(border)
  }

  _buildSky() {
    // 星空
    const N = 2600
    const p = new Float32Array(N * 3)
    const c = new Float32Array(N * 3)
    for (let i = 0; i < N; i++) {
      const r = 120 + Math.random() * 60
      const th = Math.random() * Math.PI * 2
      const ph = Math.acos(Math.random() * 0.95) // 偏上半球
      p[i * 3] = r * Math.sin(ph) * Math.cos(th)
      p[i * 3 + 1] = r * Math.cos(ph) + 2
      p[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th)
      const b = 0.4 + Math.random() * 0.6
      const warm = Math.random() < 0.2
      c[i * 3] = b * (warm ? 1 : 0.75)
      c[i * 3 + 1] = b * 0.85
      c[i * 3 + 2] = b
    }
    const g = new THREE.BufferGeometry()
    g.setAttribute('position', new THREE.BufferAttribute(p, 3))
    g.setAttribute('color', new THREE.BufferAttribute(c, 3))
    this.stars = new THREE.Points(
      g,
      new THREE.PointsMaterial({ size: 1.8, vertexColors: true, transparent: true, opacity: 0.95, depthWrite: false, sizeAttenuation: false })
    )
    this.scene.add(this.stars)

    // 远处的地球
    const earth = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: glowSpriteTexture('rgba(110,180,255,1)'), transparent: true, depthWrite: false })
    )
    earth.scale.set(18, 18, 1)
    earth.position.set(-55, 34, -80)
    this.scene.add(earth)
    const earthCore = new THREE.Mesh(
      new THREE.SphereGeometry(4.2, 32, 32),
      new THREE.MeshStandardMaterial({ color: 0x3a7bd5, emissive: 0x1e4f9e, emissiveIntensity: 0.9, roughness: 0.6 })
    )
    earthCore.position.copy(earth.position)
    this.scene.add(earthCore)
  }

  // 干扰区：程序化能量塔（没有对应模型，用电弧表现）
  _buildJammer() {
    this.jammer = new THREE.Group()
    const pillar = new THREE.Mesh(
      new THREE.CylinderGeometry(0.07, 0.16, 1.8, 6),
      new THREE.MeshStandardMaterial({ color: 0x332a1a, metalness: 0.8, roughness: 0.4, emissive: 0xf39c12, emissiveIntensity: 0.25 })
    )
    pillar.position.y = 0.9
    this.jammer.add(pillar)
    const orb = new THREE.Mesh(
      new THREE.SphereGeometry(0.16, 16, 16),
      new THREE.MeshBasicMaterial({ color: 0xffc04d })
    )
    orb.position.y = 1.95
    this.jammer.add(orb)
    // 电弧：每帧抖动的折线 x3
    this.arcs = []
    for (let k = 0; k < 3; k++) {
      const g = new THREE.BufferGeometry()
      g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(8 * 3), 3))
      const line = new THREE.Line(
        g,
        new THREE.LineBasicMaterial({ color: 0xffd34d, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false })
      )
      this.jammer.add(line)
      this.arcs.push(line)
    }
    this.jammer.visible = false
    this.scene.add(this.jammer)
  }

  // ---------- 模型 ----------
  // GLB 模型加载已禁用，所有 zone 使用占位 box。
  // 原因：GLB 模型渲染时会导致画面出现大黑块，待定位后恢复。
  _loadModels() {
    this.onProgress(100)
    this._modelsReady()
  }

  _modelsReady() {
    this._ready = true
    if (this._config) this._placeZones(this._config)
    if (this._pendingState) this.updateState(this._pendingState)
    this.onReady()
  }

  _spawn(name, scale, tint) {
    const tpl = this.models[name]
    let node
    if (tpl) {
      node = tpl.clone(true)
      node.traverse((o) => {
        if (o.isMesh) {
          o.material = o.material.clone()
          // 关键修复：模型导出时 metallic=1 / roughness=1，纯金属+全粗糙
          // 在暗环境贴图下渲染成纯黑大块。
          if (o.material.isMeshStandardMaterial) {
            // 1. 把金属度从 1 降到 0.05（接近非金属），让 baseColorTexture 的颜色能正常呈现
            if (o.material.metalness >= 0.5) o.material.metalness = 0.05
            // 2. roughness=1 时反射被打散到几乎不可见，降到 0.7 让贴图有质感
            if (o.material.roughness >= 0.9) o.material.roughness = 0.7
            // 3. 如果没有 baseColorTexture 但有 baseColor 颜色，保留
            //    如果都没有，给一个基础灰色
            if (!o.material.map && (!o.material.color || o.material.color.getHex() === 0xffffff)) {
              o.material.color = new THREE.Color(0xcccccc)
            }
            // 4. 关键：加强环境贴图影响 + emissive 兜底，避免模型渲染为纯黑
            o.material.envMapIntensity = 2.0
            if (!o.material.emissive || o.material.emissive.getHex() === 0x000000) {
              o.material.emissive = new THREE.Color(0x3a4555)
              o.material.emissiveIntensity = 0.3
            }
          }
          if (tint && !o.material.map) {
            o.material.color = new THREE.Color(tint).multiplyScalar(0.55)
            o.material.emissive = new THREE.Color(tint)
            o.material.emissiveIntensity = 0.12
          }
        }
      })
    } else {
      // 模型缺失时的占位体
      node = new THREE.Mesh(
        new THREE.BoxGeometry(0.8, 0.8, 0.8),
        new THREE.MeshStandardMaterial({ color: tint || 0x8899aa })
      )
      node.position.y = 0.4
    }
    node.scale.setScalar(scale)
    return node
  }

  setConfig(config) {
    this._config = config
    if (this._ready) this._placeZones(config)
  }

  _placeZones(config) {
    if (this._zonesPlaced) return
    this._zonesPlaced = true
    const zones = config.map?.zones || []
    const factions = config.factions || []
    const shipOrder = ['ship_a', 'ship_b', 'ship_c', 'ship_d']

    zones.forEach((z) => {
      const [gx, gy] = z.center
      const wx = gx2w(gx)
      const wz = gy2w(gy)
      const group = new THREE.Group()
      group.position.set(wx, 0, wz)
      group.userData.zoneId = z.id
      let color = KIND_COLOR[z.kind] || 0x8899aa
      let scale = 2.2

      if (z.kind === 'base') {
        const idx = shipOrder.indexOf(z.id)
        const fid = factions[idx >= 0 ? idx : 0]?.id
        color = new THREE.Color(FACTION_COLORS[fid] || '#00f2ff').getHex()
        const ship = this._spawn(MODELS[z.id] || 'ship1', 2.1, MODELS[z.id] === 'ship1' ? FACTION_COLORS[fid] : null)
        group.add(ship)
        if (fid) this.ships[fid] = { node: ship, group, state: 'idle', t: 0 }
        const l = new THREE.PointLight(color, 6, 6, 1.8)
        l.position.y = 1.6
        group.add(l)
      } else if (z.kind === 'resource') {
        const name = z.id === 'central_hi' ? MODELS.central : MODELS.resource
        scale = z.id === 'central_hi' ? 2.6 : 2.3
        group.add(this._spawn(name, scale))
      } else if (z.kind === 'relic') {
        group.add(this._spawn(z.id === 'relic_top' ? MODELS.relic_top : MODELS.relic_bottom, 2.2))
      } else if (z.kind === 'hazard') {
        group.add(this._spawn(MODELS.hazard, 2.0))
      } else if (z.kind === 'obstacle') {
        const m = this._spawn(MODELS.obstacle, 2.4)
        m.rotation.y = Math.PI / 3
        group.add(m)
        this.meteorNode = m
      } else if (z.kind === 'trap') {
        this.jammer.position.set(wx, 0, wz)
        this.jammer.visible = true
        this.jammer.userData.zoneId = z.id
      }

      // 地面光环 + 名牌
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(0.55, 0.72, 48),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.4, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false })
      )
      ring.rotation.x = -Math.PI / 2
      ring.position.y = 0.04
      group.add(ring)
      this.zoneRings[z.id] = ring

      const label = labelSprite(z.name || z.id, '#' + new THREE.Color(color).getHexString())
      label.position.y = z.kind === 'base' ? 3.1 : 2.6
      group.add(label)

      // 假投影：平贴地面的暗斑（不能用 Sprite——会竖着面向相机）
      const blob = new THREE.Mesh(
        new THREE.CircleGeometry(1.15, 32),
        new THREE.MeshBasicMaterial({ map: glowSpriteTexture('rgba(0,0,0,1)'), color: 0x000000, transparent: true, opacity: 0.4, depthWrite: false })
      )
      blob.rotation.x = -Math.PI / 2
      blob.position.y = 0.045
      group.add(blob)

      this.scene.add(group) // trap 的模型是独立的 jammer，但光环/名牌仍挂在 group 上
      this.zoneNodes[z.id] = z.kind === 'trap' ? this.jammer : group
    })
  }

  // ---------- 小车 ----------
  _makeRover(fid) {
    const color = new THREE.Color(FACTION_COLORS[fid] || '#8899aa')
    const g = new THREE.Group()
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(0.42, 0.16, 0.6),
      new THREE.MeshStandardMaterial({ color: 0x222a33, metalness: 0.85, roughness: 0.35 })
    )
    body.position.y = 0.22
    g.add(body)
    const stripe = new THREE.Mesh(
      new THREE.BoxGeometry(0.44, 0.05, 0.62),
      new THREE.MeshStandardMaterial({ color: color.clone().multiplyScalar(0.4), emissive: color, emissiveIntensity: 1.6, metalness: 0.4, roughness: 0.4 })
    )
    stripe.position.y = 0.3
    g.add(stripe)
    const wheelGeo = new THREE.CylinderGeometry(0.09, 0.09, 0.06, 12)
    const wheelMat = new THREE.MeshStandardMaterial({ color: 0x11151b, roughness: 0.9 })
    ;[-0.2, 0.02, 0.24].forEach((zz) => {
      ;[-0.24, 0.24].forEach((xx) => {
        const w = new THREE.Mesh(wheelGeo, wheelMat)
        w.rotation.z = Math.PI / 2
        w.position.set(xx, 0.09, zz - 0.02)
        g.add(w)
      })
    })
    // 桅杆信标
    const mastO = new THREE.Mesh(new THREE.SphereGeometry(0.045, 10, 10), new THREE.MeshBasicMaterial({ color }))
    mastO.position.set(0, 0.52, -0.18)
    g.add(mastO)
    const mast = new THREE.Mesh(
      new THREE.CylinderGeometry(0.012, 0.012, 0.2, 6),
      new THREE.MeshStandardMaterial({ color: 0x445566, metalness: 0.8, roughness: 0.4 })
    )
    mast.position.set(0, 0.4, -0.18)
    g.add(mast)
    const l = new THREE.PointLight(color, 2.5, 3.2, 2)
    l.position.y = 0.6
    g.add(l)

    // 月尘尾迹粒子
    const M = 90
    const pg = new THREE.BufferGeometry()
    pg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(M * 3), 3))
    const trail = new THREE.Points(
      pg,
      new THREE.PointsMaterial({ color: 0x99a8bb, size: 0.09, transparent: true, opacity: 0.55, depthWrite: false, blending: THREE.AdditiveBlending })
    )
    trail.frustumCulled = false
    this.scene.add(trail)

    g.userData = { target: new THREE.Vector3(), theta: 0, trail, trailIdx: 0, trailData: new Float32Array(M * 3).fill(9999), lastPos: new THREE.Vector3() }
    this.scene.add(g)
    return g
  }

  // ---------- 实时状态 ----------
  updateState(state) {
    if (!this._ready) {
      this._pendingState = state
      return
    }
    // 小车目标位置
    ;(state.units || []).forEach((u) => {
      if (!this.rovers[u.id]) {
        this.rovers[u.id] = this._makeRover(u.faction)
        this.rovers[u.id].userData.fid = u.faction
        this.rovers[u.id].position.set(gx2w(u.pose.x), 0, gy2w(u.pose.y))
      }
      const r = this.rovers[u.id]
      r.userData.target.set(gx2w(u.pose.x), 0, gy2w(u.pose.y))
      r.userData.theta = u.pose.theta || 0
      r.userData.status = u.status
    })

    // 区域激活态
    ;(state.zones || []).forEach((z) => {
      const ring = this.zoneRings[z.id]
      if (ring) ring.userData = { active: z.active, intensity: z.intensity ?? (z.active ? 1 : 0) }
      if (this.zoneNodes[z.id] === this.jammer) this.jammer.userData.active = z.active
    })

    // 月怒
    this.rage = state.global?.moon_rage ?? 0
    this.rageTier = state.global?.moon_tier || 'sleep'

    // 阵营状态 diff：宣布点火 / 发射 / 坠毁
    ;(state.factions || []).forEach((f) => {
      const prev = this.prevVars[f.id] || {}
      const v = f.vars || {}
      const ship = this.ships[f.id]
      if (ship) {
        if (v.launched && !prev.launched && ship.state !== 'launched') {
          ship.state = 'launching'
          ship.t = 0
          this._spawnPulse(ship.group.position, FACTION_COLORS[f.id], 2.2)
        } else if (v.crashed && !prev.crashed) {
          ship.state = 'crashed'
          ship.t = 0
          this._spawnPulse(ship.group.position, '#ff4d4d', 1.6)
        }
        ship.declaring = !!v.declaring_launch
      }
      this.prevVars[f.id] = { ...v }
    })
  }

  // 事件 -> 场景脉冲
  pushEvent(ev) {
    if (!this._ready || !ev) return
    let pos = null
    let color = '#00f2ff'
    if (ev.faction) {
      color = FACTION_COLORS[ev.faction] || color
      const unit = Object.values(this.rovers).find((r) => r.userData.fid === ev.faction)
      const ship = this.ships[ev.faction]
      pos = unit ? unit.position.clone() : ship ? ship.group.position.clone() : null
    }
    if (ev.zone && this.zoneNodes[ev.zone]) pos = this.zoneNodes[ev.zone].position.clone()
    if (!pos) return
    if (/jam|干扰/.test(ev.event_type || '')) color = '#f39c12'
    if (/crash|坠/.test(ev.event_type || '')) color = '#ff4d4d'
    this._spawnPulse(pos, color, 1.4)
  }

  // 冲击波环 + 光柱
  _spawnPulse(pos, colorHex, power = 1) {
    const color = new THREE.Color(colorHex)
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.1, 0.22, 48),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false })
    )
    ring.rotation.x = -Math.PI / 2
    ring.position.set(pos.x, 0.06, pos.z)
    this.scene.add(ring)
    const beam = new THREE.Mesh(
      new THREE.CylinderGeometry(0.12, 0.2, 7, 12, 1, true),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false })
    )
    beam.position.set(pos.x, 3.5, pos.z)
    this.scene.add(beam)
    this.fx.push({ ring, beam, t: 0, power })
  }

  // ---------- 帧循环 ----------
  _tick() {
    if (this._disposed) return
    const dt = Math.min(this.clock.getDelta(), 0.05)
    const t = this.clock.elapsedTime

    // 小车插值移动 + 尾迹
    Object.values(this.rovers).forEach((r) => {
      const u = r.userData
      const d = r.position.distanceTo(u.target)
      if (d > 0.005) {
        r.position.lerp(u.target, 1 - Math.pow(0.04, dt))
        const dir = u.target.clone().sub(r.position)
        if (dir.lengthSq() > 0.0004) {
          const want = Math.atan2(dir.x, dir.z)
          let dy = want - r.rotation.y
          while (dy > Math.PI) dy -= Math.PI * 2
          while (dy < -Math.PI) dy += Math.PI * 2
          r.rotation.y += dy * Math.min(1, dt * 6)
        }
      }
      // 移动时撒月尘
      if (r.position.distanceTo(u.lastPos) > 0.02) {
        const i = u.trailIdx = (u.trailIdx + 1) % (u.trailData.length / 3)
        u.trailData[i * 3] = r.position.x + (Math.random() - 0.5) * 0.2
        u.trailData[i * 3 + 1] = 0.06 + Math.random() * 0.12
        u.trailData[i * 3 + 2] = r.position.z + (Math.random() - 0.5) * 0.2
        u.lastPos.copy(r.position)
      }
      u.trail.geometry.attributes.position.array.set(u.trailData)
      u.trail.geometry.attributes.position.needsUpdate = true
      // 悬浮呼吸
      r.children[0] && (r.children[0].position.y = 0.22 + Math.sin(t * 2.4 + r.id) * 0.008)
    })

    // 区域光环脉冲
    for (const id in this.zoneRings) {
      const ring = this.zoneRings[id]
      const s = ring.userData || {}
      const base = s.active ? 0.35 + (s.intensity || 0) * 0.4 : 0.12
      ring.material.opacity = base + Math.sin(t * 2.2) * 0.08
      const k = 1 + Math.sin(t * 2.2) * 0.05
      ring.scale.set(k, k, 1)
    }

    // 飞船状态动画
    for (const fid in this.ships) {
      const s = this.ships[fid]
      const node = s.node
      if (s.state === 'launching') {
        s.t += dt
        const k = s.t / 5
        node.position.y = Math.pow(k, 2.2) * 42
        node.rotation.y += dt * 0.4
        if (Math.random() < 0.8) this._engineDust(s.group.position, node.position.y)
        if (k >= 1) {
          s.state = 'launched'
          node.visible = false
        }
      } else if (s.state === 'crashed') {
        s.t += dt
        node.rotation.z = Math.sin(s.t * 30) * 0.05 * Math.max(0, 1 - s.t)
        node.traverse((o) => {
          if (o.isMesh && o.material.emissive) {
            o.material.emissive.setHex(0xff2020)
            o.material.emissiveIntensity = Math.max(0, 0.8 - s.t * 0.4)
          }
        })
        if (s.t > 2) s.state = 'idle_crashed'
      } else if (s.declaring && s.state === 'idle') {
        // 宣布点火：白光呼吸
        const k = (Math.sin(t * 6) + 1) / 2
        node.traverse((o) => {
          if (o.isMesh && o.material.emissive) o.material.emissiveIntensity = 0.1 + k * 0.5
        })
      }
    }

    // 干扰塔电弧
    if (this.jammer.visible) {
      const active = this.jammer.userData.active
      this.arcs.forEach((line, k) => {
        line.visible = active !== false
        const arr = line.geometry.attributes.position.array
        const a0 = t * (1.3 + k * 0.7) + k * 2.1
        const x1 = Math.cos(a0) * 0.9
        const z1 = Math.sin(a0) * 0.9
        for (let i = 0; i < 8; i++) {
          const f = i / 7
          arr[i * 3] = THREE.MathUtils.lerp(0, x1, f) + (Math.random() - 0.5) * 0.14 * (1 - Math.abs(f - 0.5) * 2)
          arr[i * 3 + 1] = THREE.MathUtils.lerp(1.95, 0.1, f)
          arr[i * 3 + 2] = THREE.MathUtils.lerp(0, z1, f) + (Math.random() - 0.5) * 0.14
        }
        line.geometry.attributes.position.needsUpdate = true
      })
    }

    // 特效生命周期
    this.fx = this.fx.filter((f) => {
      f.t += dt
      const k = f.t / 1.1
      if (k >= 1) {
        this.scene.remove(f.ring, f.beam)
        f.ring.geometry.dispose()
        f.beam.geometry.dispose()
        return false
      }
      const r = 0.2 + k * 3.2 * f.power
      f.ring.scale.set(r / 0.16, r / 0.16, 1)
      f.ring.material.opacity = 0.95 * (1 - k)
      f.beam.material.opacity = 0.5 * (1 - k)
      f.beam.scale.set(1 - k * 0.5, 1, 1 - k * 0.5)
      return true
    })

    // 引擎月尘粒子（发射时）
    this.dusts = (this.dusts || []).filter((d) => {
      d.t += dt
      d.mesh.position.addScaledVector(d.vel, dt)
      d.mesh.material.opacity = 0.7 * (1 - d.t / d.life)
      if (d.t >= d.life) {
        this.scene.remove(d.mesh)
        return false
      }
      return true
    })

    // 月怒环境过渡
    const env = RAGE_ENV[this.rageTier] || RAGE_ENV.sleep
    this.scene.fog.color.lerp(new THREE.Color(env.fog), dt * 1.5)
    this.hemi.color.lerp(new THREE.Color(env.hemi), dt * 1.5)
    this.sun.color.lerp(new THREE.Color(env.sun), dt * 1.5)
    this.sun.intensity += (env.sunI - this.sun.intensity) * dt * 1.5
    this.rageLight.intensity += (env.red * (6 + Math.sin(t * 3) * 3) - this.rageLight.intensity) * dt * 2
    if (this.meteorNode) {
      this.meteorNode.traverse((o) => {
        if (o.isMesh && o.material.emissive) {
          o.material.emissive.setHex(0xff3010)
          o.material.emissiveIntensity = env.red * (0.35 + (Math.sin(t * 2.6) + 1) * 0.2)
        }
      })
    }
    this.bloom.strength = 0.7 + env.red * 0.35 + Math.sin(t * 3) * env.red * 0.1

    // 终局震屏
    const shakeAmp = this.rageTier === 'endgame' ? 0.05 : 0
    this.shake += (shakeAmp - this.shake) * dt * 3
    if (this.shake > 0.001) {
      this.camera.position.x += (Math.random() - 0.5) * this.shake
      this.camera.position.y += (Math.random() - 0.5) * this.shake
    }

    // 点击聚焦平滑过渡
    if (this._focusTo) {
      this.controls.target.lerp(this._focusTo, dt * 3)
      if (this.controls.target.distanceTo(this._focusTo) < 0.05) this._focusTo = null
    }

    this.stars.rotation.y += dt * 0.004
    this.controls.update()
    this.composer.render()
  }

  _engineDust(basePos, height) {
    this.dusts = this.dusts || []
    if (this.dusts.length > 120) return
    const m = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: glowSpriteTexture('rgba(255,190,120,1)'), transparent: true, opacity: 0.7, depthWrite: false, blending: THREE.AdditiveBlending })
    )
    const a = Math.random() * Math.PI * 2
    m.position.set(basePos.x + Math.cos(a) * 0.3, Math.max(0.2, height - 0.4 + basePos.y), basePos.z + Math.sin(a) * 0.3)
    const s = 0.3 + Math.random() * 0.5
    m.scale.set(s, s, 1)
    this.scene.add(m)
    this.dusts.push({ mesh: m, vel: new THREE.Vector3(Math.cos(a) * (1 + Math.random()), -0.6, Math.sin(a) * (1 + Math.random())), t: 0, life: 0.7 + Math.random() * 0.5 })
  }

  dispose() {
    this._disposed = true
    this.renderer.setAnimationLoop(null)
    window.removeEventListener('resize', this._onResize)
    this.renderer.domElement.removeEventListener('click', this._onClick)
    this.controls.dispose()
    this.scene.traverse((o) => {
      if (o.geometry) o.geometry.dispose()
      if (o.material) {
        const ms = Array.isArray(o.material) ? o.material : [o.material]
        ms.forEach((m) => {
          for (const k in m) if (m[k] && m[k].isTexture) m[k].dispose()
          m.dispose()
        })
      }
    })
    this.composer.dispose()
    this.renderer.dispose()
    if (this.renderer.domElement.parentNode) this.renderer.domElement.parentNode.removeChild(this.renderer.domElement)
  }
}
