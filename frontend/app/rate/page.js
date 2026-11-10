"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useRequireUser } from "../../lib/auth";

const DIMS = [
  ["correctness", "Correctness — is it factually right given the evidence?"],
  ["relevance", "Relevance — does it answer what was asked?"],
  ["completeness", "Completeness — does it cover what is needed?"],
  ["usefulness", "Usefulness — would it help a student?"],
];

export default function RatePage() {
  const user = useRequireUser(["rater", "admin"]);
  const [queue, setQueue] = useState(null);
  const [values, setValues] = useState({ correctness: 3, relevance: 3, completeness: 3, usefulness: 3 });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setQueue(await api("/api/v1/rater/queue"));
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!user) return <p>Loading…</p>;
  const item = queue?.[0];

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`/api/v1/rater/${item.item_id}/rating`, { method: "POST", body: values });
      setValues({ correctness: 3, relevance: 3, completeness: 3, usefulness: 3 });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Blind rating</h1>
      <p className="muted">
        You are rating responses without knowing which model produced them. Rate each dimension
        from 1 (poor) to 5 (excellent).
      </p>
      <p role="alert" className="error">{error}</p>
      {queue === null && !error && <p>Loading…</p>}
      {queue && queue.length === 0 && <p className="muted">Your queue is empty. Thank you!</p>}
      {item && (
        <>
          <p className="muted">{queue.length} item(s) remaining</p>
          <div className="card">
            <h2>Question</h2>
            <p style={{ whiteSpace: "pre-wrap" }}>{item.prompt}</p>
            {item.evidence && (
              <>
                <h2>Evidence</h2>
                <p style={{ whiteSpace: "pre-wrap" }}>{item.evidence}</p>
              </>
            )}
            <h2>Response to rate</h2>
            <p style={{ whiteSpace: "pre-wrap" }}>{item.response}</p>
          </div>
          <form className="card" onSubmit={submit}>
            {DIMS.map(([key, label]) => (
              <div key={key}>
                <label htmlFor={`r-${key}`}>{label}: <strong>{values[key]}</strong></label>
                <input
                  id={`r-${key}`}
                  type="range"
                  min="1"
                  max="5"
                  step="1"
                  value={values[key]}
                  onChange={(e) => setValues({ ...values, [key]: Number(e.target.value) })}
                />
              </div>
            ))}
            <button className="primary" type="submit" disabled={busy} style={{ marginTop: "0.75rem" }}>
              Submit rating
            </button>
          </form>
        </>
      )}
    </>
  );
}
