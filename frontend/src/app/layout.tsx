import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'IR Engineering Design & Proof-Check Platform',
  description:
    'A multi-domain Indian Railways engineering design platform: describe a component and the platform designs and proof-checks it to IR/IS practice.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-studio-base text-base text-studio-text antialiased">{children}</body>
    </html>
  )
}
