import type { Metadata } from "next";

import { Disclaimer } from "@/components/disclaimer";
import { Nav } from "@/components/nav";

import "./globals.css";

export const metadata: Metadata = {
  title: "NiveshCouncil",
  description: "Personal research cockpit for Indian equities.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className="h-full antialiased">
      <body className="flex min-h-full flex-col">
        <Nav />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-3">
            <Disclaimer />
          </div>
        </footer>
      </body>
    </html>
  );
}
