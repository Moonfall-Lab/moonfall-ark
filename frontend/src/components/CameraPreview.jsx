import { useEffect, useRef, useState } from 'react'
import { HTTP_BASE } from '../config'

export default function CameraPreview({ playerId = 'p1' }) {
  const videoRef = useRef(null)
  const [status, setStatus] = useState('opening')
  const [scan, setScan] = useState({ label: '等待二维码', raw: '', target: '' })

  useEffect(() => {
    let stream
    let cancelled = false

    async function openCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setStatus('unsupported')
        return
      }
      try {
        const probe = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        const devices = await navigator.mediaDevices.enumerateDevices()
        const macCamera = devices.find((device) => {
          if (device.kind !== 'videoinput') return false
          return /facetime|built-?in|mac|内置/i.test(device.label)
        })
        probe.getTracks().forEach((track) => track.stop())

        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            ...(macCamera ? { deviceId: { exact: macCamera.deviceId } } : { facingMode: 'user' }),
            width: { ideal: 640 },
            height: { ideal: 480 },
          },
          audio: false,
        })
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          await videoRef.current.play()
        }
        setStatus('live')
      } catch {
        setStatus('blocked')
      }
    }

    openCamera()
    return () => {
      cancelled = true
      if (stream) stream.getTracks().forEach((track) => track.stop())
    }
  }, [])

  useEffect(() => {
    let timer
    let cancelled = false
    const lastSeen = new Map()

    async function startScanner() {
      if (!('BarcodeDetector' in window)) {
        setScan({ label: '浏览器不支持二维码识别', raw: '', target: '' })
        return
      }

      const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
      const scanOnce = async () => {
        const video = videoRef.current
        if (!video || video.readyState < 2 || cancelled) return
        try {
          const codes = await detector.detect(video)
          if (!codes.length) return
          const raw = codes[0]?.rawValue || ''
          if (!raw) return

          const now = Date.now()
          const last = lastSeen.get(raw) || 0
          if (now - last < 1800) return
          lastSeen.set(raw, now)

          setScan({ label: '识别中', raw, target: '' })
          const response = await fetch(`${HTTP_BASE}/api/debug/qr`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ player_id: playerId, text: raw }),
          })
          const data = await response.json()
          const qr = data.qr || {}
          const target = data.event?.payload?.data?.target?.name || ''
          if (qr.supported && !data.ignored) {
            setScan({ label: qr.card_type === 'explore_relic' ? '探索遗迹' : '采集优先', raw, target })
          } else if (data.duplicate) {
            setScan({ label: '重复识别已忽略', raw, target: '' })
          } else {
            setScan({ label: '未支持卡片，已跳过', raw, target: '' })
          }
        } catch {
          setScan((prev) => ({ ...prev, label: '识别请求失败' }))
        }
      }

      timer = window.setInterval(scanOnce, 450)
    }

    if (status === 'live') startScanner()
    return () => {
      cancelled = true
      if (timer) window.clearInterval(timer)
    }
  }, [status, playerId])

  return (
    <div className="absolute bottom-[112px] left-3 z-40 w-[230px] border border-white/10 bg-black/75 p-2 shadow-lg backdrop-blur">
      <div className="mb-1 flex items-center justify-between font-mono text-[8px] tracking-[0.18em] text-muted">
        <span>QR CAMERA · {playerId.toUpperCase()}</span>
        <span>{status === 'live' ? 'LIVE' : status.toUpperCase()}</span>
      </div>
      <div className="relative aspect-[4/3] overflow-hidden border border-white/10 bg-black">
        <video
          ref={videoRef}
          muted
          playsInline
          className={`h-full w-full object-cover ${status === 'live' ? '' : 'opacity-20'}`}
        />
        <div className="pointer-events-none absolute inset-[18%] border border-cyan/80 shadow-[0_0_16px_rgba(99,199,196,0.25)]" />
        <div className="pointer-events-none absolute left-1/2 top-0 h-full w-px bg-white/10" />
        <div className="pointer-events-none absolute left-0 top-1/2 h-px w-full bg-white/10" />
        {status !== 'live' && (
          <div className="absolute inset-0 flex items-center justify-center px-3 text-center font-sc text-[10px] text-muted">
            {status === 'opening' && '正在打开摄像头'}
            {status === 'blocked' && '浏览器未获得摄像头权限'}
            {status === 'unsupported' && '浏览器不支持摄像头预览'}
          </div>
        )}
      </div>
      <div className="mt-1 space-y-0.5 font-mono text-[8px] leading-tight">
        <div className="flex items-center justify-between gap-2">
          <span className="text-muted">SCAN</span>
          <span style={{ color: scan.target ? '#E9B44C' : '#63C7C4' }}>{scan.label}</span>
        </div>
        {scan.raw && <div className="truncate text-muted">RAW {scan.raw}</div>}
        {scan.target && <div className="truncate" style={{ color: '#E9B44C' }}>TARGET {scan.target}</div>}
      </div>
    </div>
  )
}
