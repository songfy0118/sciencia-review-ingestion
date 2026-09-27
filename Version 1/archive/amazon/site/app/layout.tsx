import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Product Review Data", description: "Collect available Amazon reviews, inspect structured records, and export Excel, JSON, or a SQLite import." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
