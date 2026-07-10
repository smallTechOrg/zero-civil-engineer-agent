import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'IR Box Culvert Design & Proof-Check Agent',
  description:
    'Designs single-cell RCC box culverts from natural language to IRS practice and proof-checks its own design.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-100 text-base text-slate-900 antialiased">{children}</body>
    </html>
  )
}
