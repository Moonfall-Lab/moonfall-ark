import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

// 鼠标锁定方框尺寸
const SCAN_SIZE = 200

export default function Landing({ onEnter }) {
  const scanPos = useRef({ x: -9999, y: -9999 })
  const [phase, setPhase] = useState('stable') // stable → observing → locked → expanding → entered
  const [hovered, setHovered] = useState(false)
  const [containerSize, setContainerSize] = useState({ w: 0, h: 0 })
  const [btnCenter, setBtnCenter] = useState(null)
  const containerRef = useRef(null)
  const bg2Ref = useRef(null) // 直接操作 DOM 避免 React re-render
  const scanBoxRef = useRef(null)
  const btnRef = useRef(null)
  const hasMoved = useRef(false)

  // 背景对齐调试 GUI（Ctrl+B 切换）
  const [showAlign, setShowAlign] = useState(false)
  const [bg1, setBg1] = useState({ x: 50, y: 50, scale: 100 }) // background-position % 和 size %
  const [bg2, setBg2] = useState({ x: 50, y: 50, scale: 100 })

  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey && (e.key === 'b' || e.key === 'B')) {
        e.preventDefault()
        setShowAlign((s) => !s)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // 监听容器尺寸 + 按钮位置
  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect()
        setContainerSize({ w: rect.width, h: rect.height })
        if (btnRef.current) {
          const br = btnRef.current.getBoundingClientRect()
          setBtnCenter({ x: br.left + br.width / 2 - rect.left, y: br.top + br.height / 2 - rect.top })
        }
      }
    }
    update()
    window.addEventListener('resize', update)
    const timer = setTimeout(update, 100)
    return () => {
      window.removeEventListener('resize', update)
      clearTimeout(timer)
    }
  }, [phase])

  // 实时跟随鼠标 — 用 ref + 直接操作 DOM，绕过 React re-render（60fps 不卡）
  const updateScanBox = useCallback((x, y, w, h) => {
    const el = bg2Ref.current
    const box = scanBoxRef.current
    if (!el || !containerRef.current) return
    const cw = containerRef.current.clientWidth
    const ch = containerRef.current.clientHeight
    const left = Math.max(0, x - w / 2)
    const top = Math.max(0, y - h / 2)
    const right = Math.max(0, cw - x - w / 2)
    const bottom = Math.max(0, ch - y - h / 2)
    el.style.clipPath = `inset(${top}px ${right}px ${bottom}px ${left}px round 2px)`
    if (box) {
      box.style.left = `${x - w / 2}px`
      box.style.top = `${y - h / 2}px`
      box.style.width = `${w}px`
      box.style.height = `${h}px`
    }
  }, [])

  const onMouseMove = useCallback((e) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    scanPos.current = { x, y }
    // locked 时不在鼠标位置，而是在按钮位置
    if (phaseRef.current !== 'locked') {
      updateScanBox(x, y, SCAN_SIZE, SCAN_SIZE)
    }
    if (!hasMoved.current) {
      hasMoved.current = true
      setPhase('observing')
    }
  }, [updateScanBox])

  // phase 的 ref（让 onMouseMove 能读到最新 phase 而不重建回调）
  const phaseRef = useRef(phase)
  useEffect(() => { phaseRef.current = phase }, [phase])

  // 按钮 hover → 锁定状态（扫描框吸附到按钮）
  const handleBtnEnter = () => {
    setHovered(true)
    if (phase === 'observing') setPhase('locked')
  }
  const handleBtnLeave = () => {
    setHovered(false)
    if (phase === 'locked') setPhase('observing')
  }

  // 点击 ENTER → 扩展转场（缩短到 1 秒）
  const handleEnter = () => {
    setPhase('expanding')
    setTimeout(() => {
      setPhase('entered')
      setTimeout(() => onEnter?.(), 500)
    }, 1000)
  }

  const isExpanding = phase === 'expanding' || phase === 'entered'

  // locked 时扫描框吸附到按钮中心（通过 effect 触发一次）
  // expanding 时 clip-path 扩展为全屏
  useEffect(() => {
    if (phase === 'locked' && btnCenter) {
      updateScanBox(btnCenter.x, btnCenter.y, 300, 80)
    } else if (phase === 'expanding' || phase === 'entered') {
      if (bg2Ref.current) {
        bg2Ref.current.style.clipPath = 'circle(150% at 50% 50%)'
      }
    }
  }, [phase, btnCenter, updateScanBox])

  return (
    <div
      ref={containerRef}
      className="relative w-screen h-screen overflow-hidden cursor-crosshair"
      onMouseMove={onMouseMove}
      style={{ background: '#0B0E10' }}
    >
      {/* ============ 背景层（扫描框只影响背景，不影响文字） ============ */}

      {/* 底层：lunar-background1 — bg-cover 填满屏幕，right center 保留月球 */}
      <div
        className="absolute inset-0 bg-cover bg-no-repeat transition-opacity duration-700"
        style={{
          backgroundImage: `url(/assets/landing/lunar-background1.jpg)`,
          backgroundColor: '#0B0E10',
          backgroundPosition: 'right center',
          opacity: isExpanding ? 0 : 1,
        }}
      />

      {/* 顶层：lunar-background2 — clip-path 由 ref 直接操作，不经过 React re-render */}
      <div
        ref={bg2Ref}
        className="absolute inset-0 bg-cover bg-no-repeat"
        style={{
          backgroundImage: `url(/assets/landing/lunar-background2.png?v=8)`,
          backgroundColor: '#0B0E10',
          backgroundPosition: 'right center',
          clipPath: 'inset(9999px)', // 初始不可见
        }}
      />

      {/* 扫描框边框：位置由 ref 直接操作，避免 mousemove 触发 re-render */}
      <AnimatePresence>
        {(phase === 'observing' || phase === 'locked') && !isExpanding && (
          <motion.div
            ref={scanBoxRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="absolute pointer-events-none"
            style={{
              width: SCAN_SIZE,
              height: SCAN_SIZE,
            }}
          >
            {/* 四角定位标 */}
            {[
              'top-0 left-0 border-t border-l',
              'top-0 right-0 border-t border-r',
              'bottom-0 left-0 border-b border-l',
              'bottom-0 right-0 border-b border-r',
            ].map((cls, i) => (
              <div
                key={i}
                className={`absolute w-4 h-4 ${cls}`}
                style={{ borderColor: 'rgba(240,68,62,0.6)' }}
              />
            ))}
            {/* 扫描线（locked 时加速） */}
            <motion.div
              className="absolute left-0 right-0 h-px"
              style={{ background: 'rgba(240,68,62,0.5)', boxShadow: '0 0 4px rgba(240,68,62,0.3)' }}
              animate={{ top: ['0%', '100%', '0%'] }}
              transition={{ duration: phase === 'locked' ? 1.5 : 2.8, repeat: Infinity, ease: 'easeInOut' }}
            />
            {/* 框内红色叠加 */}
            <div
              className="absolute inset-0"
              style={{ background: 'rgba(240,68,62,0.1)' }}
            />
            {/* 状态文字 */}
            <div className="absolute -top-5 left-0 text-[8px] font-mono tracking-[0.2em] text-[#F0443E]/70 whitespace-nowrap">
              {phase === 'locked' ? 'ACCESS LOCKING' : 'SIGNAL DETECTED'}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* expanding 红色叠加 */}
      <AnimatePresence>
        {isExpanding && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.12 }}
            className="absolute inset-0 pointer-events-none"
            style={{ background: '#F0443E' }}
          />
        )}
      </AnimatePresence>

      {/* ============ 内容层（永远在扫描框之上，不被遮挡） ============ */}
      <div className="absolute inset-0 flex flex-col pointer-events-none" style={{ zIndex: 10 }}>
        {/* 中央内容 */}
        <div className="flex-1 flex flex-col items-center justify-center px-6">
          {/* MOONFALL 大标题 */}
          <motion.div
            initial={{ opacity: 0, y: 20, letterSpacing: '0.3em' }}
            animate={{ opacity: 1, y: 0, letterSpacing: '0.15em' }}
            transition={{ duration: 1.2, delay: 0.3 }}
            className="text-center"
          >
            <h1
              className="font-condensed font-bold leading-none"
              style={{
                fontSize: 'clamp(44px, 9vw, 140px)',
                color: '#E7E1D6',
                textShadow: isExpanding ? '0 0 30px rgba(240,68,62,0.4)' : 'none',
              }}
            >
              MOONFALL
            </h1>
          </motion.div>

          {/* 平台定位（放大） */}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 0.8, y: 0 }}
            transition={{ duration: 1, delay: 1 }}
            className="mt-8 text-center"
          >
            <div className="font-sc font-medium tracking-wider text-white/80" style={{ fontSize: 'clamp(16px, 2.5vw, 28px)' }}>
              具身 AI 游戏创作平台
            </div>
          </motion.div>

          {/* 按钮 + 转场文字：共用固定高度容器，避免按钮消失后内容塌陷 */}
          <div className="mt-10 flex flex-col items-center gap-1.5 pointer-events-auto" style={{ minHeight: '70px' }}>
            {/* 状态标签 */}
            <div className="text-[7px] font-mono tracking-[0.25em] text-white/25 mb-1 h-[10px]">
              {phase !== 'stable' && !isExpanding ? (hovered ? 'LUNAR ACCESS / READY' : 'LUNAR ACCESS / STANDBY') : ''}
            </div>

            <AnimatePresence mode="wait">
              {phase !== 'stable' && !isExpanding ? (
                <motion.div
                  key="btn"
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3 }}
                >
                  <button
                    ref={btnRef}
                    onClick={handleEnter}
                    onMouseEnter={handleBtnEnter}
                    onMouseLeave={handleBtnLeave}
                    className="group relative px-10 py-3.5 transition-all duration-300 overflow-hidden"
                    style={{
                      background: 'transparent',
                      borderTop: '1px solid rgba(231,225,214,0.25)',
                      borderBottom: '1px solid rgba(231,225,214,0.25)',
                    }}
                  >
                    {/* hover 红色充能层 */}
                    <div
                      className="absolute inset-0 transition-transform duration-500"
                      style={{
                        background: 'rgba(240,68,62,0.1)',
                        transform: hovered ? 'scaleX(1)' : 'scaleX(0)',
                        transformOrigin: 'left',
                      }}
                    />
                    {/* 底部充能线 */}
                    <div
                      className="absolute bottom-0 left-0 h-[2px] transition-transform duration-500"
                      style={{
                        background: '#F0443E',
                        width: '100%',
                        transform: hovered ? 'scaleX(1)' : 'scaleX(0)',
                        transformOrigin: 'left',
                        boxShadow: '0 0 6px rgba(240,68,62,0.6)',
                      }}
                    />
                    <span
                      className="relative font-mono text-sm tracking-[0.2em] font-semibold transition-colors duration-300"
                      style={{ color: hovered ? '#F0443E' : '#E7E1D6' }}
                    >
                      ENTER MOONFALL
                    </span>
                    <span
                      className="relative ml-2 text-xs transition-all duration-300"
                      style={{
                        color: hovered ? '#F0443E' : 'rgba(231,225,214,0.5)',
                        display: 'inline-block',
                        transform: hovered ? 'translateX(4px)' : 'translateX(0)',
                      }}
                    >
                      ↗
                    </span>
                  </button>
                </motion.div>
              ) : isExpanding ? (
                <motion.div
                  key="descent"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="flex justify-center"
                >
                  <div className="text-[10px] font-mono tracking-[0.3em] text-[#F0443E]">
                    INITIATING DESCENT
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        </div>

        {/* 底部操作提示（低亮，3秒后淡出） */}
        <BottomHint phase={phase} isExpanding={isExpanding} />
      </div>

      {/* 背景对齐调试面板（Ctrl+B 切换） */}
      {showAlign && (
        <AlignPanel
          bg1={bg1} setBg1={setBg1}
          bg2={bg2} setBg2={setBg2}
          onClose={() => setShowAlign(false)}
        />
      )}
    </div>
  )
}

// 背景对齐调试面板
function AlignPanel({ bg1, setBg1, bg2, setBg2, onClose }) {
  const Slider = ({ label, value, onChange, min, max }) => (
    <div className="flex items-center gap-2">
      <span className="text-[9px] font-mono text-white/50 w-16">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="flex-1 h-1 accent-cyan-400"
      />
      <span className="text-[9px] font-mono text-white/70 w-10 text-right tabular-nums">{value}</span>
    </div>
  )

  return (
    <div className="fixed top-4 right-4 z-[100] w-[280px] bg-black/85 border border-white/10 p-4 text-white/70 backdrop-blur-md">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] font-mono tracking-widest text-white/80">ALIGNMENT GUI</span>
        <button onClick={onClose} className="text-[10px] text-white/40 hover:text-white/70">✕</button>
      </div>

      {/* BG1 控制 */}
      <div className="mb-3">
        <div className="text-[8px] font-mono text-cyan-400/70 mb-1.5 tracking-wider">BACKGROUND 1 (STABLE)</div>
        <div className="space-y-1.5">
          <Slider label="X %" value={bg1.x} onChange={(v) => setBg1({ ...bg1, x: v })} min={0} max={100} />
          <Slider label="Y %" value={bg1.y} onChange={(v) => setBg1({ ...bg1, y: v })} min={0} max={100} />
          <Slider label="Size %" value={bg1.scale} onChange={(v) => setBg1({ ...bg1, scale: v })} min={50} max={150} />
        </div>
      </div>

      {/* BG2 控制 */}
      <div className="mb-3">
        <div className="text-[8px] font-mono text-red-400/70 mb-1.5 tracking-wider">BACKGROUND 2 (RAGE)</div>
        <div className="space-y-1.5">
          <Slider label="X %" value={bg2.x} onChange={(v) => setBg2({ ...bg2, x: v })} min={0} max={100} />
          <Slider label="Y %" value={bg2.y} onChange={(v) => setBg2({ ...bg2, y: v })} min={0} max={100} />
          <Slider label="Size %" value={bg2.scale} onChange={(v) => setBg2({ ...bg2, scale: v })} min={50} max={150} />
        </div>
      </div>

      {/* 同步按钮 */}
      <button
        onClick={() => setBg2(bg1)}
        className="w-full text-[9px] font-mono tracking-wider text-white/50 border border-white/10 py-1.5 hover:bg-white/5 transition-colors"
      >
        COPY BG1 → BG2
      </button>

      <div className="mt-2 text-[7px] font-mono text-white/20 text-center">
        Ctrl+B 切换 · 调整到两张图月亮对齐
      </div>
    </div>
  )
}

// 底部提示：3秒后自动淡出
function BottomHint({ phase, isExpanding }) {
  const [visible, setVisible] = useState(true)
  useEffect(() => {
    const t = setTimeout(() => setVisible(false), 3000)
    return () => clearTimeout(t)
  }, [])
  if (isExpanding) return null
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="pb-6 text-center"
        >
          <div className="text-[7px] font-mono tracking-[0.25em] text-white/20">
            {phase === 'stable' ? 'MOVE TO PROBE THE SURFACE' : '移动鼠标探测月面'}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
