import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Zer0 Rail Agent — smallTech',
  description:
    'Zer0 Rail Agent by smallTech (smalltech.in): describe a railway engineering component and the agent designs and proof-checks it to IR/IS practice.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-studio-base text-base text-studio-text antialiased">{children}</body>
    </html>
  )
}
