/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        void: '#090B0C',
        panel: '#121619',
        'panel-strong': '#1A1F22',
        'lunar-white': '#E7E1D6',
        'muted-text': '#8E9497',
        cyan: '#63C7C4',
        amber: '#E9B44C',
        'danger-red': '#F0523D',
        'critical-red': '#FF2F2F',
      },
      fontFamily: {
        mono: ['IBM Plex Mono', 'ui-monospace', 'monospace'],
        sc: ['Noto Sans SC', 'sans-serif'],
        condensed: ['Oswald', 'sans-serif'],
      },
      keyframes: {
        shake: {
          '0%,100%': { transform: 'translateX(0)' },
          '25%': { transform: 'translateX(-3px)' },
          '75%': { transform: 'translateX(3px)' },
        },
        flicker: {
          '0%,100%': { opacity: 1 },
          '50%': { opacity: 0.7 },
        },
        pulseWarn: {
          '0%,100%': { opacity: 0.4 },
          '50%': { opacity: 1 },
        },
      },
      animation: {
        shake: 'shake 0.4s ease-in-out infinite',
        flicker: 'flicker 2s ease-in-out infinite',
        'pulse-warn': 'pulseWarn 1.2s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
