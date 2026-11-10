"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../../lib/api";
import { useRequireUser } from "../../../lib/auth";

export default function PrivacyPage() {
  const user = useRequireUser();
  const [defaults, setDefaults] = useState({ mode: "local_only", persist: false });
  const [consents, setConsents] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    try {
      const [c, p] = await Promise.all([api("/api/v1/consents"), api("/api/v1/institutional-policy")]);
      setConsents(c);
      setPolicy(p);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    if (!user) return;
    try {
      const saved = JSON.parse(window.localStorage.getItem("sr_defaults") || "null");
      if (saved) setDefaults(saved);
    } catch {
      /* ignore */
    }
    load();
  }, [user, load]);

  if (!user) return <p>Loading…</p>;

  const saveDefaults = (next) => {
    setDefaults(next);
    try {
      window.localStorage.setItem("sr_defaults", JSON.stringify(next));
    } catch {
      /* ignore */
    }
  };

  const active = (consents || []).filter((c) => !c.revoked_at && new Date(c.expires_at) > new Date());

  return (
    <>
      <h1>Privacy</h1>
      <p role="alert" className="error">{error}</p>
      <p role="status" className="ok">{note}</p>

      <div className="card">
        <h2>Defaults for new sessions</h2>
        <label htmlFor="mode">Default mode</label>
        <select id="mode" value={defaults.mode} onChange={(e) => saveDefaults({ ...defaults, mode: e.target.value })}>
          <option value="local_only">Local-only (recommended)</option>
          <option value="cloud_allowed">Cloud allowed</option>
        </select>
        <label className="row">
          <input
            type="checkbox"
            checked={defaults.persist}
            onChange={(e) => saveDefaults({ ...defaults, persist: e.target.checked })}
          />
          Keep conversation history (opt-in). By default session content is deleted after 60
          minutes of inactivity.
        </label>
      </div>

      <div className="card">
        <h2>Institutional policy</h2>
        {policy && (
          <p>
            Cloud models are <strong>{policy.allow_cloud ? "permitted" : "prohibited"}</strong> by your
            institution.{" "}
            {policy.forbid_labels?.length > 0 && <>Forbidden labels: {policy.forbid_labels.join(", ")}.</>}{" "}
            Policy always overrides consent.
          </p>
        )}
      </div>

      <div className="card">
        <h2>Active consents</h2>
        {consents === null ? (
          <p>Loading…</p>
        ) : active.length === 0 ? (
          <p className="muted">No active consents. Nothing sensitive can be sent to a cloud model.</p>
        ) : (
          <div className="scroll-x">
            <table>
              <thead><tr><th>Model</th><th>Expires</th><th></th></tr></thead>
              <tbody>
                {active.map((c) => (
                  <tr key={c.id}>
                    <td>{c.destination_model_id}</td>
                    <td>{new Date(c.expires_at).toLocaleString()}</td>
                    <td>
                      <button
                        onClick={async () => {
                          await api(`/api/v1/consents/${c.id}`, { method: "DELETE" });
                          await load();
                        }}
                      >
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Delete my data</h2>
        <p className="muted">Immediately removes all your sessions, messages, documents and chunks.</p>
        <button
          className="danger"
          onClick={async () => {
            if (!window.confirm("Delete all your sessions and documents now? This cannot be undone.")) return;
            await api("/api/v1/me/data", { method: "DELETE" });
            setNote("All session content deleted.");
          }}
        >
          Delete all my session data
        </button>
      </div>
    </>
  );
}
