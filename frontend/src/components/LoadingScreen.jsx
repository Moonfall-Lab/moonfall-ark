export default function LoadingScreen({ status }) {
  return (
    <div className="w-screen h-screen flex flex-col items-center justify-center gap-3" style={{ background: '#090B0C' }}>
      <div className="font-condensed text-4xl font-bold tracking-[0.3em] text-lunar-white">MOONFALL</div>
      <div className="text-muted text-xs font-sc">
        {status === 'mock' ? '演示数据加载中…' : '连接 Runtime 中…'}
      </div>
      <div className="text-muted/50 text-[10px] font-mono">
        ws://127.0.0.1:8000/ws · ?mock=1 离线预览
      </div>
    </div>
  )
}
