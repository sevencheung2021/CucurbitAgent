import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        teal: { brand: '#0F766E', accent: '#0D9488' },
        slate: { muted: '#475569', card: '#64748B' },
      },
      maxWidth: { content: '1280px' },
    },
  },
  plugins: [],
};
export default config;
