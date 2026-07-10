export default function LoadingScreen({ status }) {
  return (
    <div className="w-screen h-screen bg-void text-glacier font-mono flex flex-col items-center justify-center gap-4">
      <div className="text-4xl font-black tracking-[0.4em] glow-cyan animate-pulse">MOONFALL</div>
      <div className="text-white/50 text-sm">
        {status === 'mock' ? '演示数据加载中…' : '连接 Runtime 中…'}
      </div>
      <div className="text-white/30 text-xs">
        默认 ws://127.0.0.1:8000/ws · 加 ?mock=1 可离线预览 · ?host=IP:8000 指定后端
      </div>
    </div>
  )
}
