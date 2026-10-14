import './globals.css';

export const metadata = {
  title: 'Open Higgsfield AI - Self-Hosted Studio',
  description: 'Local AI image, video, cinema and lip-sync studio. Model availability is reported by your self-hosted backend.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
