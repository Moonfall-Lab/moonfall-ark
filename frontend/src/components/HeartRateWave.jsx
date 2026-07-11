import { useEffect, useRef } from 'react'

// Canvas 心率波形。心率越高，振幅与频率越大，传达紧张感。
export default function HeartRateWave({ bpm = 0, color = '#2ecc71', compact = false }) {
  const ref = useRef(null)
  const bpmRef = useRef(bpm)
  bpmRef.current = bpm

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let raf
    let t = 0

    const draw = () => {
      const b = bpmRef.current || 0
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      const w = (canvas.width = Math.max(1, Math.round(canvas.clientWidth * ratio)))
      const h = (canvas.height = Math.max(1, Math.round(canvas.clientHeight * ratio)))
      ctx.clearRect(0, 0, w, h)

      const baseline = h * 0.55
      const beatWidth = Math.max(42, (60 / Math.max(45, b || 72)) * 75 * ratio)
      const amp = h * Math.min(0.42, 0.25 + Math.max(0, b - 60) / 400)
      ctx.beginPath()
      for (let x = 0; x < w; x++) {
        const phase = ((x + t) % beatWidth) / beatWidth
        const pulse =
          0.08 * Math.exp(-Math.pow((phase - 0.18) / 0.045, 2)) -
          0.18 * Math.exp(-Math.pow((phase - 0.34) / 0.018, 2)) +
          1.0 * Math.exp(-Math.pow((phase - 0.39) / 0.012, 2)) -
          0.3 * Math.exp(-Math.pow((phase - 0.43) / 0.018, 2)) +
          0.16 * Math.exp(-Math.pow((phase - 0.66) / 0.07, 2))
        const y = baseline - pulse * amp
        if (x === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.shadowBlur = 8
      ctx.shadowColor = color
      ctx.stroke()

      t += (Math.max(45, b || 72) / 60) * 0.85 * ratio
      raf = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(raf)
  }, [color])

  return <canvas ref={ref} className={`block w-full opacity-80 ${compact ? 'h-full' : 'h-[30px]'}`} />
}
