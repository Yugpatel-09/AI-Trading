import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: 'class',
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          navy: '#0A141F',
          dark: '#0D1B2A',
          card: '#132235',
          border: '#1F334A',
          teal: '#0D9488',
          'teal-light': '#14B8A6',
          'teal-accent': '#4CC9AC',
        },
        trade: {
          profit: '#10B981', // Green used only for profit
          loss: '#EF4444',   // Red used only for loss
          neutral: '#94A3B8',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
export default config;
