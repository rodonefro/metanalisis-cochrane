/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        cochrane: {
          50: '#f0f7ff',
          100: '#e0effe',
          500: '#005eb8',
          600: '#004f9e',
          700: '#003d7a',
        },
      },
    },
  },
  plugins: [],
}
