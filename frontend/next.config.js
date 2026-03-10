/** @type {import('next').NextConfig} */
const backendPort = process.env.NEXT_PUBLIC_BACKEND_PORT || '8000';
const backendHost = process.env.NEXT_PUBLIC_BACKEND_HOST || 'localhost';

module.exports = {
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `http://${backendHost}:${backendPort}/api/:path*`,
      },
    ];
  },
};
