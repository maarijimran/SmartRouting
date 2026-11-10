"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "../lib/auth";

export default function Home() {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (ready && user) router.replace("/chat");
  }, [ready, user, router]);
  return (
    <>
      <h1>SmartRoute</h1>
      <p>
        A privacy-constrained router for academic document assistance. Each question is routed
        to a local or cloud model; cloud models are only ever considered when your privacy
        settings allow it, and every answer shows why that model was chosen.
      </p>
      <div className="row">
        <Link href="/login"><button className="primary">Sign in</button></Link>
        <Link href="/register"><button>Create an account</button></Link>
      </div>
    </>
  );
}
