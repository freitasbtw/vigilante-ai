import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vigilante.AI",
  description: "Monitoramento de segurança do trabalho com visão computacional",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
