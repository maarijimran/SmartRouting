"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "../lib/auth";

const LINKS = [
  { href: "/chat", label: "Chat", roles: ["user", "rater", "admin"] },
  { href: "/settings/keys", label: "Keys", roles: ["user", "rater", "admin"] },
  { href: "/settings/models", label: "Models", roles: ["user", "rater", "admin"] },
  { href: "/settings/privacy", label: "Privacy", roles: ["user", "rater", "admin"] },
  { href: "/analytics", label: "Analytics", roles: ["user", "rater", "admin"] },
  { href: "/rate", label: "Rate", roles: ["rater", "admin"] },
  { href: "/admin", label: "Admin", roles: ["admin"] },
];

export default function Nav() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  return (
    <nav className="nav" aria-label="Main">
      <Link className="brand" href={user ? "/chat" : "/"}>SmartRoute</Link>
      {user &&
        LINKS.filter((l) => l.roles.includes(user.role)).map((l) => (
          <Link key={l.href} href={l.href} aria-current={pathname === l.href ? "page" : undefined}>
            {l.label}
          </Link>
        ))}
      <span className="spacer" />
      {user ? (
        <>
          <span className="muted">{user.email} · {user.role}</span>
          <button
            onClick={async () => {
              await logout();
              router.push("/login");
            }}
          >
            Sign out
          </button>
        </>
      ) : (
        <>
          <Link href="/login">Sign in</Link>
          <Link href="/register">Register</Link>
        </>
      )}
    </nav>
  );
}
