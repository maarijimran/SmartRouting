"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "../../lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError("");
    try {
      await login(form.get("email"), form.get("password"));
      router.push("/chat");
    } catch (err) {
      setError(
        err.status === 429
          ? "Too many failed attempts. This account is temporarily locked; try again later."
          : err.status === 403
            ? "This account is disabled."
            : "Unable to sign in. Check your email and password."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "2rem auto" }}>
      <h1>Sign in to SmartRoute</h1>
      <form onSubmit={submit}>
        <label htmlFor="email">Email</label>
        <input id="email" name="email" type="email" autoComplete="email" required />
        <label htmlFor="password">Password</label>
        <input id="password" name="password" type="password" autoComplete="current-password" required />
        <p role="alert" className="error">{error}</p>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="muted">No account? <Link href="/register">Register</Link></p>
    </div>
  );
}
