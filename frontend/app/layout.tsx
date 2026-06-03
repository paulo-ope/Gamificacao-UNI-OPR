import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Gamificação Operacional OPR",
  description: "Remuneração variável por produtividade e saúde operacional."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}

