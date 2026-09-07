import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        teal: { brand: '#334155'  /* placeholder — use your own brand color */, accent: '#475569'  /* placeholder */ },
        slate: { muted: '#475569', card: '#64748B' },
      },
      maxWidth: { content: '1280px' },
    },
  },
  plugins: [],
};
export default config;
