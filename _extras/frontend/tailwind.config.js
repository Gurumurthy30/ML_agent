/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        shell: '#1F1E1D',
        sidebar: '#181716',
        chat: '#262624',
        card: '#2D2C2A',
        primary: '#F5F4F0',
        muted: '#9B9A96',
        accent: {
          DEFAULT: '#DA7756',
          hover: '#e58564',
          active: '#c86849',
          muted: '#da775620',
          glow: '#da775635',
        },
        border: {
          DEFAULT: '#3A3936',
          subtle: '#2E2D2A',
          strong: '#4A4844',
        },
        error: {
          DEFAULT: '#E5484D',
          soft: '#e5484d20',
        },
        success: {
          DEFAULT: '#46A758',
          soft: '#46a75820',
        },
        warning: {
          DEFAULT: '#F7CE46',
          soft: '#f7ce4620',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      fontSize: {
        base: ['15px', { lineHeight: '1.6' }],
        sm: ['13.5px', { lineHeight: '1.5' }],
        xs: ['12px', { lineHeight: '1.4' }],
      },
      maxWidth: {
        chat: '760px',
      },
      transitionTimingFunction: {
        claude: 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
}
