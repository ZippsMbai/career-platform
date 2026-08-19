/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#10151c",
        paper: "#f5f1e6",
        paperdark: "#eae3d2",
        stamp: "#c08829",
        teal: "#3e6e67",
        flag: "#a8432f",
        textdark: "#201b12",
        textmuted: "#6b6252",
      },
      fontFamily: {
        serif: ["Georgia", "Iowan Old Style", "serif"],
        mono: ["JetBrains Mono", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};
