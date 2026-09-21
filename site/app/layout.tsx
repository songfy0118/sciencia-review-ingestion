import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Review Collector | Sciencia", description: "Collect available Amazon reviews, inspect structured records, and export CSV or JSON." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
