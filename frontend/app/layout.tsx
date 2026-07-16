import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "LedgerGuard",
  description: "Upload invoices for deterministic discrepancy analysis.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
