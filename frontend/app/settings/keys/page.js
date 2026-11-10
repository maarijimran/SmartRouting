"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { useRequireUser } from "../../../lib/auth";

const OPENROUTER = "https://openrouter.ai/api/v1";

export default function KeysPage() {
  const user = useRequireUser();
  const [items, setItems] = useState(null);
  const [provider, setProvider] = useState("openrouter");
  const [baseUrl, setBaseUrl] = useState(OPENROUTER);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setItems(await api("/api/v1/connections"));
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    if (user) load();
  }, [user, load]);

  if (!user) return <p>Loading…</p>;

  async function add(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true);
    setError("");
    setNote("");
    try {
      const cap = data.get("cap");
      await api("/api/v1/connections", {
        method: "POST",
        body: {
          provider,
          base_url: baseUrl,
          label: data.get("label"),
          api_key: data.get("api_key"),
          ...(cap ? { monthly_budget_usd: Number(cap) } : {}),
        },
      });
      form.reset(); // the key is never kept in the page after saving
      setBaseUrl(provider === "openrouter" ? OPENROUTER : "");
      setNote("Saved. The key is encrypted at rest and will only show as …last4.");
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function test(id) {
    setError("");
    try {
      const out = await api(`/api/v1/connections/${id}/test`, { method: "POST" });
      setNote(`Connection test: ${out.status}`);
      await load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function remove(id) {
    if (!window.confirm("Delete this connection? Models using it become unavailable.")) return;
    await api(`/api/v1/connections/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <>
      <h1>Provider keys</h1>
      <p className="muted">
        Bring your own OpenRouter (or OpenAI-compatible) key. One OpenRouter key reaches both GPT
        and Claude models. Keys are encrypted, only decrypted at the moment a request is sent to
        the cloud, and never displayed again.
      </p>
      <div className="card">
        <h2>Add a connection</h2>
        <form onSubmit={add}>
          <label htmlFor="provider">Provider</label>
          <select
            id="provider"
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setBaseUrl(e.target.value === "openrouter" ? OPENROUTER : "");
            }}
          >
            <option value="openrouter">OpenRouter (default)</option>
            <option value="openai_compat">Custom OpenAI-compatible</option>
          </select>
          <label htmlFor="base">Base URL</label>
          <input id="base" type="text" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} required />
          <label htmlFor="label">Label</label>
          <input id="label" name="label" type="text" maxLength={100} required />
          <label htmlFor="api_key">API key</label>
          <input id="api_key" name="api_key" type="password" autoComplete="off" minLength={8} required />
          <label htmlFor="cap">Monthly cap in USD (optional hard stop)</label>
          <input id="cap" name="cap" type="number" min="0" step="0.01" />
          <p role="alert" className="error">{error}</p>
          <p role="status" className="ok">{note}</p>
          <button className="primary" type="submit" disabled={busy}>Save connection</button>
        </form>
      </div>

      <h2>Your connections</h2>
      {items === null ? (
        <p>Loading…</p>
      ) : items.length === 0 ? (
        <p className="muted">No connections yet. Without one, only local models can answer.</p>
      ) : (
        <div className="scroll-x">
          <table>
            <thead>
              <tr><th>Label</th><th>Provider</th><th>Key</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id}>
                  <td>{c.label}</td>
                  <td>{c.provider}</td>
                  <td>…{c.last4}</td>
                  <td><span className={`chip ${c.status === "ok" ? "public" : c.status === "failed" ? "bad" : ""}`}>{c.status}</span></td>
                  <td className="row">
                    <button onClick={() => test(c.id)}>Test</button>
                    <button className="danger" onClick={() => remove(c.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
