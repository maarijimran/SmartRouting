"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useAuth } from "../../lib/auth";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (form.get("password") !== form.get("confirm")) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await register(form.get("email"), form.get("password"));
      router.push("/settings/keys");
    } catch (err) {
      setError(err.status === 409 ? "An account with this email already exists." : err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card" style={{ maxWidth: 420, margin: "2rem auto" }}>
      <h1>Create your account</h1>
      <form onSubmit={submit}>
        <label htmlFor="email">Email</label>
        <input id="email" name="email" type="email" autoComplete="email" required />
        <label htmlFor="password">Password (at least 10 characters)</label>
        <input id="password" name="password" type="password" minLength={10} autoComplete="new-password" required />
        <label htmlFor="confirm">Confirm password</label>
        <input id="confirm" name="confirm" type="password" minLength={10} autoComplete="new-password" required />
        <p role="alert" className="error">{error}</p>
        <button className="primary" type="submit" disabled={busy}>
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
      <p className="muted">Already registered? <Link href="/login">Sign in</Link></p>
    </div>
  );
}
