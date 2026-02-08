/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        github: '#2ea44f',
        youtube: '#ff0000',
      },
    },
  },
  plugins: [],
}