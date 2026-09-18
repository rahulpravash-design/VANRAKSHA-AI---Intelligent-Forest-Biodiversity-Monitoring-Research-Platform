import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";

import { Providers } from "@/lib/Providers";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "VANRAKSHA AI — Forest Biodiversity Intelligence",
    template: "%s · VANRAKSHA AI",
  },
  description:
    "An intelligent forest biodiversity monitoring and research platform — computer vision, acoustic AI, GIS, IoT and multimodal fusion.",
};

export const viewport: Viewport = {
  themeColor: "#0b1f19",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
