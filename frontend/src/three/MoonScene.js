// MoonFall 3D 实时场景引擎（three.js）
// 职责：月面环境 / 模型摆放 / 小车实时移动 / 事件特效 / 月怒氛围。
// React 侧只需调用 mount / setConfig / updateState / pushEvent / dispose。
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { FACTION_COLORS } from '../lib/factions'

const GRID = 12 // 12x12 棋盘（保留用于兼容）

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

// 真实场地：80cm × 60cm，坐标单位 = cm / 10（1 世界单位 = 10cm）
// 坐标原点在左下角，中心偏移到世界原点
const FIELD_W = 8 // 80cm / 10
const FIELD_H = 6 // 60cm / 10
const gx2w = (gx) => gx - FIELD_W / 2 // 场地坐标 -> 世界坐标
const gy2w = (gy) => gy - FIELD_H / 2

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
  const font = '600 32px "IBM Plex Mono", monospace'
  g.font = font
  const w = Math.ceil(g.measureText(text).width) + 24
  c.width = w
  c.height = 48
  const g2 = c.getContext('2d')
  g2.font = font
  g2.fillStyle = 'rgba(5,8,12,0.6)'
  g2.beginPath()
  g2.roundRect(0, 4, w, 40, 6)
  g2.fill()
  g2.fillStyle = color
  g2.textBaseline = 'middle'
  g2.fillText(text, 12, 26)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  const m = new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false, opacity: 0.8 })
  const s = new THREE.Sprite(m)
  s.scale.set(w / 130, 0.48, 1)
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
    this.armFx = [] // 机械臂锁定/攻击预测
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
    // 高面数 GLB + 高 DPI 会显著增加帧缓冲压力。
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 1.05
    container.appendChild(this.renderer.domElement)

    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0x05070c)
    this.scene.fog = new THREE.FogExp2(0x0a0e16, 0.014)
    this.engineDustTexture = glowSpriteTexture('rgba(255,190,120,1)')
    // 关键：PBR 金属材质必须有环境贴图，否则反射为纯黑
    // 用 envMapIntensity 在材质级别加强环境光
    const pmrem = new THREE.PMREMGenerator(this.renderer)
    this.scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture
    pmrem.dispose()

    this.camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 300)
    // 导播视角：约 60° 俯视，保证四角飞船和中央目标同时可见。
    this.camera.position.set(9, 8, 9) // 适配 8×6 矩形场地

    this.renderer.domElement.style.touchAction = 'none' // 触屏/触控板双指捏合缩放交给 OrbitControls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.target.set(0, 0.6, 0)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.06
    this.controls.autoRotate = true
    this.controls.autoRotateSpeed = 0.5
    this.controls.minDistance = 4
    this.controls.maxDistance = 25
    this.controls.maxPolarAngle = Math.PI * 0.47
    this.controls.addEventListener('start', () => (this.controls.autoRotate = false))

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

    // 带起伏的月面：场地区域保持平整，四周隆起随机丘陵
    const size = 80
    const seg = 120
    const geo = new THREE.PlaneGeometry(size, size, seg, seg)
    const pos = geo.attributes.position
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i)
      const y = pos.getY(i)
      // 场地是矩形 8×6，用 max(|x|/(halfW), |y|/(halfH)) 判断是否在场地外
      const halfW = FIELD_W / 2 + 1.5
      const halfH = FIELD_H / 2 + 1.5
      const d = Math.max(Math.abs(x) / halfW, Math.abs(y) / halfH)
      const edge = THREE.MathUtils.smoothstep(d, 1, size / 2 / Math.max(halfW, halfH))
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

    // 四角切角的月面工程平台（矩形 8×6，匹配真实场地 80×60cm）
    const halfW = FIELD_W / 2 + 0.22
    const halfH = FIELD_H / 2 + 0.22
    const cut = 0.8
    const platformShape = new THREE.Shape()
    platformShape.moveTo(-halfW + cut, -halfH)
    platformShape.lineTo(halfW - cut, -halfH)
    platformShape.lineTo(halfW, -halfH + cut)
    platformShape.lineTo(halfW, halfH - cut)
    platformShape.lineTo(halfW - cut, halfH)
    platformShape.lineTo(-halfW + cut, halfH)
    platformShape.lineTo(-halfW, halfH - cut)
    platformShape.lineTo(-halfW, -halfH + cut)
    platformShape.closePath()

    const deck = new THREE.Mesh(
      new THREE.ExtrudeGeometry(platformShape, { depth: 0.28, bevelEnabled: true, bevelSegments: 2, bevelSize: 0.07, bevelThickness: 0.05 }),
      new THREE.MeshStandardMaterial({ color: 0x252b2e, metalness: 0.5, roughness: 0.7, envMapIntensity: 0.7 })
    )
    deck.rotation.x = Math.PI / 2
    deck.position.y = -0.06
    this.scene.add(deck)

    const inset = new THREE.Mesh(
      new THREE.ShapeGeometry(platformShape),
      new THREE.MeshStandardMaterial({ color: 0x4a5052, roughness: 0.93, metalness: 0.08 })
    )
    inset.rotation.x = -Math.PI / 2
    inset.position.y = 0.018
    this.scene.add(inset)

    // 定位线降级为工业板缝：小格极弱，每 3 格一条主结构线。
    // 使用矩形场地的 halfW/halfH
    const minorPts = []
    const majorPts = []
    const gridMax = Math.max(FIELD_W, FIELD_H)
    const gridSteps = Math.ceil(gridMax)
    for (let i = 0; i <= gridSteps; i++) {
      const v = i - gridMax / 2
      // X 方向线：限制在 halfH 范围内
      const limitX = Math.abs(v) > halfH - cut ? halfH - (Math.abs(v) - (halfH - cut)) : halfH
      // Z 方向线：限制在 halfW 范围内
      const limitZ = Math.abs(v) > halfW - cut ? halfW - (Math.abs(v) - (halfW - cut)) : halfW
      const target = i % 3 === 0 ? majorPts : minorPts
      target.push(-limitZ, 0, v, limitZ, 0, v)
      target.push(v, 0, -limitX, v, 0, limitX)
    }
    const minorGeo = new THREE.BufferGeometry()
    minorGeo.setAttribute('position', new THREE.Float32BufferAttribute(minorPts, 3))
    this.gridLines = new THREE.LineSegments(
      minorGeo,
      new THREE.LineBasicMaterial({ color: 0x8a9293, transparent: true, opacity: 0.04, depthWrite: false })
    )
    this.gridLines.position.y = 0.035
    this.scene.add(this.gridLines)

    const majorGeo = new THREE.BufferGeometry()
    majorGeo.setAttribute('position', new THREE.Float32BufferAttribute(majorPts, 3))
    const majorLines = new THREE.LineSegments(
      majorGeo,
      new THREE.LineBasicMaterial({ color: 0x9aa2a3, transparent: true, opacity: 0.1, depthWrite: false })
    )
    majorLines.position.y = 0.038
    this.scene.add(majorLines)

    // 边缘只保留短段状态灯，不再使用完整青色 AR 外框。
    // 不对称：部分灯段损坏或被尘土遮住，营造真实工程感。
    const edgeLights = new THREE.Group()
    const makeLightMat = (opacity) => new THREE.MeshBasicMaterial({ color: 0x69c9c7, transparent: true, opacity })
    const dimMat = new THREE.MeshBasicMaterial({ color: 0x4a5253, transparent: true, opacity: 0.18 })
    const lightConfigs = [
      { opacity: 0.55 }, { opacity: 0.4 }, { opacity: 0.15, dim: true },
      { opacity: 0.5 }, { opacity: 0.3 }, { opacity: 0.55 },
    ]
    let lcIdx = 0
    ;[-2.5, 0, 2.5].forEach((v) => {
      ;[-1, 1].forEach((side) => {
        const cfg = lightConfigs[lcIdx % lightConfigs.length]
        lcIdx++
        const mat = cfg.dim ? dimMat : makeLightMat(cfg.opacity)
        const horizontal = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.035, 0.07), mat)
        horizontal.position.set(v, 0.055, side * (halfH - 0.08))
        edgeLights.add(horizontal)
        const vertical = new THREE.Mesh(new THREE.BoxGeometry(0.07, 0.035, 0.8), mat.clone())
        vertical.position.set(side * (halfW - 0.08), 0.055, v)
        edgeLights.add(vertical)
      })
    })
    this.edgeLights = edgeLights
    this.scene.add(edgeLights)

    // 静态积尘贴花：底盘与月面交界处的不规则尘土覆盖
    // 不是粒子，只是平贴地面的半透明面片
    const dustCanvas = document.createElement('canvas')
    dustCanvas.width = dustCanvas.height = 128
    const dg = dustCanvas.getContext('2d')
    const dgrad = dg.createRadialGradient(64, 64, 10, 64, 64, 60)
    dgrad.addColorStop(0, 'rgba(150,142,130,0.5)')
    dgrad.addColorStop(0.5, 'rgba(120,112,102,0.25)')
    dgrad.addColorStop(1, 'rgba(100,94,88,0)')
    dg.fillStyle = dgrad
    dg.fillRect(0, 0, 128, 128)
    const dustTex = new THREE.CanvasTexture(dustCanvas)
    dustTex.colorSpace = THREE.SRGBColorSpace
    const dustMat = new THREE.MeshBasicMaterial({
      map: dustTex,
      transparent: true,
      opacity: 0.15,
      depthWrite: false,
      side: THREE.DoubleSide,
    })
    // 底盘四边各放 2 片不规则尘土
    const dustPositions = []
    for (let i = 0; i < 4; i++) {
      const angle = (i / 4) * Math.PI * 2
      const cx = Math.cos(angle) * (halfW + 0.8)
      const cz = Math.sin(angle) * (halfH + 0.8)
      dustPositions.push({ x: cx, z: cz, rot: Math.random() * Math.PI, scale: 2.5 + Math.random() * 1.5 })
      dustPositions.push({ x: cx * 0.6, z: cz * 0.6, rot: Math.random() * Math.PI, scale: 1.8 + Math.random() * 1.2 })
    }
    dustPositions.forEach((dp) => {
      const dustMesh = new THREE.Mesh(
        new THREE.PlaneGeometry(dp.scale, dp.scale),
        dustMat.clone()
      )
      dustMesh.rotation.x = -Math.PI / 2
      dustMesh.rotation.z = dp.rot
      dustMesh.position.set(dp.x, 0.04, dp.z)
      this.scene.add(dustMesh)
    })
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
  // 所有 GLB 顺序加载；单个资源失败时，对应区域自动使用占位体。
  async _loadModels() {
    const names = [...new Set(Object.values(MODELS))]
    const loader = new GLTFLoader()

    // 顺序加载，避免多个大模型同时抢占网络和解析资源。
    for (let i = 0; i < names.length; i++) {
      const name = names[i]
      try {
        const gltf = await loader.loadAsync(`/assets/models/${name}.glb`)
        this.models[name] = gltf.scene
      } catch (error) {
        console.error(`Failed to load ${name}.glb; using placeholder instead.`, error)
      }
      this.onProgress(Math.round(((i + 1) / names.length) * 100))
    }

    if (!this._disposed) this._modelsReady()
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
      // 干扰区没有对应 GLB，不在 3D 场景中生成程序化占位物。
      if (z.kind === 'trap') return

      const [gx, gy] = z.center
      const wx = gx2w(gx)
      const wz = gy2w(gy)
      const group = new THREE.Group()
      group.position.set(wx, 0, wz)
      group.userData.zoneId = z.id
      let color = KIND_COLOR[z.kind] || 0x8899aa
      let scale = 1.0 // 真实物体缩放（1 世界单位 = 10cm）

      if (z.kind === 'base') {
        const idx = shipOrder.indexOf(z.id)
        const fid = factions[idx >= 0 ? idx : 0]?.id
        color = new THREE.Color(FACTION_COLORS[fid] || '#00f2ff').getHex()

        // 四角玩家区改为边缘工业泊位，颜色只出现在短灯条上。
        const outward = new THREE.Vector2(wx, wz).normalize()
        const dock = new THREE.Mesh(
          new THREE.BoxGeometry(2.05, 0.075, 1.28),
          new THREE.MeshStandardMaterial({ color: 0x3a4144, metalness: 0.42, roughness: 0.78 })
        )
        dock.rotation.y = Math.atan2(outward.x, outward.y) + Math.PI / 2
        dock.position.y = 0.045
        group.add(dock)

        const dockLight = new THREE.Mesh(
          new THREE.BoxGeometry(0.92, 0.035, 0.07),
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.72 })
        )
        dockLight.rotation.y = dock.rotation.y
        dockLight.position.set(outward.x * 0.55, 0.095, outward.y * 0.55)
        group.add(dockLight)

        const ship = this._spawn(MODELS[z.id] || 'ship1', 2.1, MODELS[z.id] === 'ship1' ? FACTION_COLORS[fid] : null)
        group.add(ship)
        if (fid) this.ships[fid] = { node: ship, group, state: 'idle', t: 0 }
        const l = new THREE.PointLight(color, 6, 6, 1.8)
        l.position.y = 1.6
        group.add(l)
      } else if (z.kind === 'resource') {
        // 高能站用 fuel_station 模型，普通能源站用 resource_station
        const isHigh = z.type === 'high_energy_station' || z.id === 'central_hi'
        const name = isHigh ? MODELS.central : MODELS.resource
        scale = isHigh ? 1.2 : 1.0 // 真实物体半径 ~5.5cm → 缩放到合理 3D 尺寸
        group.add(this._spawn(name, scale))
      } else if (z.kind === 'relic') {
        group.add(this._spawn(MODELS.relic_top, 1.0))
      } else if (z.kind === 'hazard') {
        group.add(this._spawn(MODELS.hazard, 2.0))
      } else if (z.kind === 'obstacle') {
        const m = this._spawn(MODELS.obstacle, 2.4)
        m.rotation.y = Math.PI / 3
        group.add(m)
        this.meteorNode = m
      }

      // 功能区保留克制的嵌入式定位环；玩家区已使用泊位灯条。
      if (z.kind !== 'base') {
        const ring = new THREE.Mesh(
          new THREE.RingGeometry(0.55, 0.7, 32), // 真实半径 ~5.5cm
          new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false })
        )
        ring.rotation.x = -Math.PI / 2
        ring.position.y = 0.055
        group.add(ring)
        this.zoneRings[z.id] = ring
      }

      // 常驻标签只保留四个玩家和中央核心，避免遮挡模型。
      let labelText = null
      if (z.kind === 'base') {
        const idx = shipOrder.indexOf(z.id)
        labelText = factions[idx >= 0 ? idx : 0]?.id?.toUpperCase() || z.id
      } else if (z.id === 'central_hi') {
        labelText = 'ARK'
      }
      if (labelText) {
        const label = labelSprite(labelText, '#' + new THREE.Color(color).getHexString())
        label.position.y = z.kind === 'base' ? 2.2 : 1.9
        group.add(label)
      }

      // 假投影：平贴地面的暗斑（不能用 Sprite——会竖着面向相机）
      const blob = new THREE.Mesh(
        new THREE.CircleGeometry(1.15, 32),
        new THREE.MeshBasicMaterial({ map: glowSpriteTexture('rgba(0,0,0,1)'), color: 0x000000, transparent: true, opacity: 0.4, depthWrite: false })
      )
      blob.rotation.x = -Math.PI / 2
      blob.position.y = 0.045
      group.add(blob)

      this.scene.add(group)
      this.zoneNodes[z.id] = group
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

    // 阵营状态 diff：起飞改为前端手动触发，避免 Runtime/mock 自动发射干扰调试。
    ;(state.factions || []).forEach((f) => {
      const prev = this.prevVars[f.id] || {}
      const v = f.vars || {}
      const ship = this.ships[f.id]
      if (ship) {
        if (v.crashed && !prev.crashed) {
          ship.state = 'crashed'
          ship.t = 0
          this._spawnPulse(ship.group.position, '#ff4d4d', 1.6)
        }
        ship.declaring = false
      }
      this.prevVars[f.id] = { ...v }
    })
  }

  launchShip(fid) {
    const ship = this.ships[fid]
    if (!ship || ship.state === 'launching') return
    ship.node.visible = true
    ship.node.position.y = 0
    ship.node.rotation.z = 0
    ship.state = 'launching'
    ship.t = 0
    this._spawnPulse(ship.group.position, FACTION_COLORS[fid], 2.2)
  }

  resetShips() {
    Object.values(this.ships).forEach((ship) => {
      ship.state = 'idle'
      ship.t = 0
      ship.declaring = false
      ship.node.visible = true
      ship.node.position.y = 0
      ship.node.rotation.z = 0
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
    const isArmThreat = /arm|meteor|jam|boss|attack|strike/i.test(ev.event_type || '')
    if (isArmThreat) {
      pos ||= new THREE.Vector3(0, 0, 0)
      this._spawnArmLock(pos)
    }
    if (!pos) return
    if (/jam|干扰/.test(ev.event_type || '')) color = '#f39c12'
    if (/crash|坠/.test(ev.event_type || '')) color = '#ff4d4d'
    this._spawnPulse(pos, color, 1.4)
  }

  // 冲击波环 + 细光柱（弱化版：透明度更低，光柱更细）
  _spawnPulse(pos, colorHex, power = 1) {
    const color = new THREE.Color(colorHex)
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.1, 0.22, 48),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false })
    )
    ring.rotation.x = -Math.PI / 2
    ring.position.set(pos.x, 0.06, pos.z)
    this.scene.add(ring)
    // 光柱改为细圆柱（更克制）
    const beam = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.08, 5, 8, 1, true),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.25, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, depthWrite: false })
    )
    beam.position.set(pos.x, 2.5, pos.z)
    this.scene.add(beam)
    this.fx.push({ ring, beam, t: 0, power })
  }

  // 机械臂锁定版：地面锁定圈 + 扫描带 + 细光柱 + 目标高亮
  // 替代旧版"完整大圆环"，更精准、危险、有"来源"
  _spawnArmLock(pos) {
    const group = new THREE.Group()
    group.position.set(pos.x, 0, pos.z)

    // 1. 地面锁定圈（外圈）：断续扫描环（不完整闭合，更像"正在工作"）
    const outerRing = new THREE.Mesh(
      new THREE.RingGeometry(0.78, 0.86, 48, 1, 0, Math.PI * 1.7),
      new THREE.MeshBasicMaterial({
        color: 0xa6e2e0,
        transparent: true,
        opacity: 0.55,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    )
    outerRing.rotation.x = -Math.PI / 2
    outerRing.rotation.z = -Math.PI * 0.35 // 缺口朝向扫描源
    outerRing.position.y = 0.085
    group.add(outerRing)

    // 2. 内圈实心锁定环（细，更冷）
    const innerRing = new THREE.Mesh(
      new THREE.RingGeometry(0.6, 0.66, 64),
      new THREE.MeshBasicMaterial({
        color: 0xc9f0ee,
        transparent: true,
        opacity: 0.35,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    )
    innerRing.rotation.x = -Math.PI / 2
    innerRing.position.y = 0.08
    group.add(innerRing)

    // 3. 目标脚下小锁定圈（最贴近模型）
    const targetRing = new THREE.Mesh(
      new THREE.RingGeometry(0.35, 0.4, 32),
      new THREE.MeshBasicMaterial({
        color: 0xff3b30,
        transparent: true,
        opacity: 0.7,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    )
    targetRing.rotation.x = -Math.PI / 2
    targetRing.position.y = 0.075
    group.add(targetRing)

    // 4. 细光柱（从天空投下）：上宽下窄锥体
    const beamGeo = new THREE.ConeGeometry(0.4, 8, 16, 1, true)
    const beamMat = new THREE.MeshBasicMaterial({
      color: 0xa6e2e0,
      transparent: true,
      opacity: 0.15,
      side: THREE.DoubleSide,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })
    const beam = new THREE.Mesh(beamGeo, beamMat)
    beam.position.y = 4
    beam.rotation.x = Math.PI // 尖端朝下
    group.add(beam)

    // 5. 内核细亮柱（更明亮、集中在中央）
    const innerBeam = new THREE.Mesh(
      new THREE.CylinderGeometry(0.04, 0.06, 7, 8, 1, true),
      new THREE.MeshBasicMaterial({
        color: 0xeafbff,
        transparent: true,
        opacity: 0.55,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    )
    innerBeam.position.y = 3.5
    group.add(innerBeam)

    // 6. 扫描带（关键动效）：从原点方向扫入、缓慢推进
    const scanLine = new THREE.Mesh(
      new THREE.PlaneGeometry(0.05, 1.4),
      new THREE.MeshBasicMaterial({
        color: 0xd7ffff,
        transparent: true,
        opacity: 0.8,
        side: THREE.DoubleSide,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      })
    )
    scanLine.rotation.x = -Math.PI / 2
    scanLine.position.y = 0.09
    group.add(scanLine)

    // 7. 来源虚线（从画外天空指向目标）：提示"谁在打"
    const origin = new THREE.Vector3(FIELD_W / 2 + 2, 3.5, -FIELD_H / 2 - 2)
    const points = [origin, new THREE.Vector3(0, 0.16, 0)]
    const lineGeo = new THREE.BufferGeometry().setFromPoints(points)
    const line = new THREE.Line(
      lineGeo,
      new THREE.LineDashedMaterial({
        color: 0xff3b30,
        dashSize: 0.32,
        gapSize: 0.22,
        transparent: true,
        opacity: 0.55,
        depthWrite: false,
      })
    )
    line.computeLineDistances()

    this.scene.add(group)
    this.scene.add(line)
    this.armFx.push({
      group,
      outerRing,
      innerRing,
      targetRing,
      beam,
      innerBeam,
      scanLine,
      line,
      t: 0,
      life: 3.2,
    })
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
        // 保持起飞姿态稳定，避免导出法线/材质在旋转时闪黑。
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
      f.ring.material.opacity = 0.55 * (1 - k)
      f.beam.material.opacity = 0.25 * (1 - k)
      f.beam.scale.set(1 - k * 0.5, 1, 1 - k * 0.5)
      return true
    })

    this.armFx = this.armFx.filter((f) => {
      f.t += dt
      const remaining = Math.max(0, 1 - f.t / f.life)
      const k = f.t / f.life // 0 → 1 进度

      // 危险升级：最后 30% 由冷青转为红色
      const danger = Math.max(0, (k - 0.7) / 0.3)
      const r = 0xa6e2e0
      const g = 0x64 + (0x3b - 0x64) * danger // 0x64 → 0x3b
      const b = 0xe0 + (0x30 - 0xe0) * danger
      const tintColor = (Math.floor(r) << 16) | (Math.floor(g) << 8) | Math.floor(b)

      // 主锁定环：轻微脉冲
      const pulse = 1 + Math.sin(f.t * 8) * 0.06
      f.innerRing.scale.setScalar(pulse)
      f.innerRing.material.opacity = 0.35 * remaining + 0.15
      f.innerRing.material.color.setHex(tintColor)

      // 外圈扫描环：缓慢自转
      f.outerRing.rotation.z += dt * 0.6
      f.outerRing.material.opacity = 0.4 * remaining + 0.1
      f.outerRing.material.color.setHex(tintColor)

      // 目标脚下小圈：高频脉动（最显眼）
      const targetPulse = 1 + Math.sin(f.t * 14) * 0.18
      f.targetRing.scale.setScalar(targetPulse)
      f.targetRing.material.opacity = (0.55 + danger * 0.4) * remaining

      // 扫描带：按角度自转（最关键的动效）
      const scanRadius = 0.74
      f.scanLine.position.x = Math.cos(f.t * 1.4) * scanRadius
      f.scanLine.position.z = Math.sin(f.t * 1.4) * scanRadius
      f.scanLine.rotation.z = -f.t * 1.4 + Math.PI / 2
      f.scanLine.material.opacity = 0.7 * remaining

      // 细光柱：呼吸式衰减
      f.beam.material.opacity = 0.13 * remaining
      f.beam.scale.set(1, 0.8 + Math.sin(f.t * 6) * 0.05, 1)
      f.beam.material.color.setHex(tintColor)
      f.innerBeam.material.opacity = 0.5 * remaining
      f.innerBeam.material.color.setHex(tintColor)

      // 来源虚线
      f.line.material.opacity = 0.5 * remaining
      f.line.material.color.setHex(danger > 0.5 ? 0xff3b30 : tintColor)

      if (f.t < f.life) return true
      this.scene.remove(f.group, f.line)
      f.group.traverse((o) => {
        if (o.geometry) o.geometry.dispose()
        if (o.material) o.material.dispose()
      })
      f.line.geometry.dispose()
      f.line.material.dispose()
      return false
    })

    // 引擎月尘粒子（发射时）
    this.dusts = (this.dusts || []).filter((d) => {
      d.t += dt
      d.mesh.position.addScaledVector(d.vel, dt)
      d.mesh.material.opacity = 0.7 * (1 - d.t / d.life)
      if (d.t >= d.life) {
        this.scene.remove(d.mesh)
        d.mesh.material.dispose()
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
    // 稳定模式：直接渲染，绕过 Bloom/EffectComposer 的额外帧缓冲。
    this.renderer.render(this.scene, this.camera)
  }

  _engineDust(basePos, height) {
    this.dusts = this.dusts || []
    if (this.dusts.length > 120) return
    const m = new THREE.Sprite(
      new THREE.SpriteMaterial({ map: this.engineDustTexture, transparent: true, opacity: 0.7, depthWrite: false, blending: THREE.AdditiveBlending })
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
    this.engineDustTexture.dispose()
    this.renderer.dispose()
    if (this.renderer.domElement.parentNode) this.renderer.domElement.parentNode.removeChild(this.renderer.domElement)
  }
}
