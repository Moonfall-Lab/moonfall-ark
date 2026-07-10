import { useEffect, useRef } from 'react'

// Canvas 心率波形。心率越高，振幅与频率越大，传达紧张感。
export default function HeartRateWave({ bpm = 0, color = '#2ecc71' }) {
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
      const w = (canvas.width = canvas.clientWidth * 2)
      const h = (canvas.height = 60)
      ctx.clearRect(0, 0, w, h)

      const amp = Math.min(22, 5 + Math.max(0, b - 60) * 0.4)
      const freq = 0.02 + Math.max(0, b - 60) * 0.0022
      ctx.beginPath()
      for (let x = 0; x < w; x++) {
        const wave = Math.sin(x * freq + t) * amp * 0.35
        const blip = Math.exp(-Math.pow((x % 130) - 65, 2) / 26) * amp * 1.5
        const y = h / 2 - wave - blip
        if (x === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      }
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.shadowBlur = 8
      ctx.shadowColor = color
      ctx.stroke()

      t += 0.14 + Math.max(0, b - 60) * 0.004
      raf = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(raf)
  }, [color])

  return <canvas ref={ref} className="w-full h-[30px] opacity-80" />
}
