import { THEMES } from '../themes'

export default function ThemeSwitcher({ theme, onChange }) {
  return (
    <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-50 flex gap-1 p-1 rounded-full bg-black/60 border border-white/10 backdrop-blur">
      {THEMES.map((t) => {
        const active = t.key === theme
        return (
          <button
            key={t.key}
            onClick={() => onChange(t.key)}
            className={`px-4 py-1.5 rounded-full text-xs transition ${
              active ? 'text-black' : 'text-white/60 hover:text-white'
            }`}
            style={active ? { background: 'var(--accent)' } : undefined}
          >
            {t.label}
          </button>
        )
      })}
    </div>
  )
}
