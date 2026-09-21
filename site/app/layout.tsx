import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = { title: "Sciencia Review Ingestion", description: "A live feasibility prototype for structured product review ingestion." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
