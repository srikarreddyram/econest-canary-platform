/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'brand': '#45f3ff',
        'brand-glow': 'rgba(69, 243, 255, 0.5)',
        'success': '#39FF14',
        'danger': '#FF0055',
        'warning': '#FFD700',
        'bg-dark': '#0B0C10',
        'bg-card': 'rgba(30, 32, 40, 0.6)',
        'border-color': 'rgba(255, 255, 255, 0.1)',
        'text-primary': '#FFFFFF',
        'text-secondary': '#8B949E'
      },
      fontFamily: {
        'sans': ['Inter', '-apple-system', 'sans-serif'],
        'mono': ['SFMono-Regular', 'Consolas', 'monospace']
      }
    },
  },
  plugins: [],
}
