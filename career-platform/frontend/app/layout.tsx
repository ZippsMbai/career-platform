import "./globals.css";

export const metadata = {
  title: "Career Intelligence Platform",
  description: "Resume vs. job fit analysis and application tracking",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
