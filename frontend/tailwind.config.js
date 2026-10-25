/** Tailwind compiled at build time (was the runtime CDN), so CSP needs no inline styles. */
/** @type {import('tailwindcss').Config} */
export default {
  // Every file that spells out class names, including data arrays of class strings
  content: ['./index.html', './*.{ts,tsx}', './components/**/*.{ts,tsx}', './services/**/*.{ts,tsx}', './config/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      colors: {
        wpi: {
          red: '#AC2B37',
          redDark: '#8B1F29',
          grey: '#A9B0B7',
          darkGrey: '#383838',
        },
      },
    },
  },
  plugins: [],
};
