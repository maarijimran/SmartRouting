"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { useRequireUser } from "../../../lib/auth";

export default function ModelsPage() {
  const user = useRequireUser();
  const [models, setModels] = useState(null);
  const [connections, setConnections] = useState([]);
  const [cheap, setCheap] = useState("");
  const [strong, setStrong] = useState("");
  const [connection, setConnection] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    try {
      const [m, c] = await Promise.all([api("/api/v1/models/catalog"), api("/api/v1/connections")]);
      setModels(m);
      setConnections(c);
      if (c[0]) setConnection((cur) => cur || c[0].id);
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!user) return <p>Loading…</p>;
  const cloud = (models || []).filter((m) => m.kind === "cloud");
  const local = (models || []).filter((m) => m.kind === "local");

  async function save(event) {
    event.preventDefault();
    setError("");
    setNote("");
    try {
      await api("/api/v1/models/preferences", {
        method: "PUT",
        body: [
          { model_id: cheap, connection_id: connection, tier: "cheap" },
          { model_id: strong, connection_id: connection, tier: "strong" },
        ],
      });
      setNote("Saved. Routing will consider these two cloud models for your requests.");
    } catch (e) {
      setError(e.message);
    }
  }

  const price = (m) =>
    m.price
      ? `$${m.price.input_per_mtok}/M in · $${m.price.output_per_mtok}/M out (snapshot ${m.price.captured_at.slice(0, 10)})`
      : "price unknown — cannot be used";

  return (
    <>
      <h1>Models</h1>
      <div className="card">
        <h2>Local model</h2>
        {local.length === 0 && <p className="muted">No local model is registered. Ask an admin to add one.</p>}
        {local.map((m) => (
          <p key={m.id}>
            <strong>{m.slug}</strong> · context {m.context_limit} ·{" "}
            <span className={`chip ${m.health?.ok ? "public" : "bad"}`}>
              {m.health ? (m.health.ok ? "healthy" : "unreachable") : "not yet probed"}
            </span>
          </p>
        ))}
      </div>

      <div className="card">
        <h2>Cloud models</h2>
        {connections.length === 0 ? (
          <p className="muted">Add a provider key first (Settings → Keys), then choose models here.</p>
        ) : cloud.length < 2 ? (
          <p className="muted">An admin must register at least two cloud models (cheap and strong).</p>
        ) : (
          <form onSubmit={save}>
            <label htmlFor="conn">Connection</label>
            <select id="conn" value={connection} onChange={(e) => setConnection(e.target.value)} required>
              {connections.map((c) => <option key={c.id} value={c.id}>{c.label} (…{c.last4})</option>)}
            </select>
            <label htmlFor="cheap">Cheap model</label>
            <select id="cheap" value={cheap} onChange={(e) => setCheap(e.target.value)} required>
              <option value="" disabled>Choose…</option>
              {cloud.map((m) => <option key={m.id} value={m.id}>{m.slug} — {price(m)}</option>)}
            </select>
            <label htmlFor="strong">Strong model</label>
            <select id="strong" value={strong} onChange={(e) => setStrong(e.target.value)} required>
              <option value="" disabled>Choose…</option>
              {cloud.filter((m) => m.id !== cheap).map((m) => (
                <option key={m.id} value={m.id}>{m.slug} — {price(m)}</option>
              ))}
            </select>
            <p role="alert" className="error">{error}</p>
            <p role="status" className="ok">{note}</p>
            <button className="primary" type="submit" disabled={!cheap || !strong}>Save choice</button>
          </form>
        )}
        {models && (
          <div className="scroll-x">
            <table>
              <thead><tr><th>Model</th><th>Context</th><th>Price</th></tr></thead>
              <tbody>
                {cloud.map((m) => (
                  <tr key={m.id}><td>{m.slug}</td><td>{m.context_limit}</td><td>{price(m)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
