import createNextIntlPlugin from 'next-intl/plugin';

/** @type {import('next').NextConfig} */
const apiOrigin = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

const nextConfig = {
  images: { unoptimized: true },
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${apiOrigin}/api/:path*`,
      },
    ];
  },
  // Avoid long-lived HTML cache pointing at deleted /_next chunks after rebuild
  // (stale document + new DeployGuard races contributed to URL flashing).
  // NOTE: Next matches header rules in order and the LAST matching rule wins
  // for a given key — so the specific asset rules below override the blanket
  // no-store for hashed chunks and /vendor, keeping megabyte-scale JS
  // (molstar / plotly) cacheable while HTML stays fresh.
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'private, no-cache, no-store, max-age=0, must-revalidate',
          },
        ],
      },
      {
        source: '/_next/static/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=31536000, immutable' },
        ],
      },
      {
        source: '/vendor/:path*',
        headers: [
          { key: 'Cache-Control', value: 'public, max-age=604800' },
        ],
      },
    ];
  },
};

export default withNextIntl(nextConfig);
