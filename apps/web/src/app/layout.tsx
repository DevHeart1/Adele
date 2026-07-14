import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Adele Web",
  description: "Browser and cloud Adele experience.",
};

const navItems = [
  { href: "/", label: "Dashboard" },
  { href: "/memory", label: "Memory" },
  { href: "/tasks", label: "Tasks" },
  { href: "/connectors", label: "Connectors" },
  { href: "/browser", label: "Browser" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <aside className="sidebar">
            <div className="brand">
              <strong>Adele Web</strong>
              <span>Cloud memory and browser automation</span>
            </div>
            <nav className="nav-list" aria-label="Main navigation">
              {navItems.map((item) => (
                <Link className="nav-link" href={item.href} key={item.href}>
                  {item.label}
                </Link>
              ))}
            </nav>
          </aside>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
