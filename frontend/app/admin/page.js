"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useRequireUser } from "../../lib/auth";

const TABS = ["Registry", "Institutional policy", "Policies", "Budgets", "Users", "Raters", "Retention"];

function useLoad(path, enabled = true) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    try {
      setData(await api(path));
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [path]);
  useEffect(() => {
    if (enabled) reload();
  }, [enabled, reload]);
  return { data, error, reload };
}

function Status({ error, note }) {
  return (
    <>
      <p role="alert" className="error">{error}</p>
      <p role="status" className="ok">{note}</p>
    </>
  );
}

function Registry() {
  const { data, error, reload } = useLoad("/api/v1/models/catalog?include_disabled=true");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const run = async (fn, msg) => {
    setErr("");
    try {
      await fn();
      setNote(msg);
      await reload();
    } catch (e) {
      setErr(e.message);
    }
  };
  return (
    <>
      <Status error={error || err} note={note} />
      <div className="scroll-x">
        <table>
          <thead><tr><th>Slug</th><th>Kind</th><th>Provider model</th><th>Context</th><th>Price (in/out per M)</th><th>Enabled</th><th></th></tr></thead>
          <tbody>
            {(data || []).map((m) => (
              <tr key={m.id}>
                <td>{m.slug}</td><td>{m.kind}</td><td>{m.provider_model || "—"}</td><td>{m.context_limit}</td>
                <td>{m.price ? `${m.price.input_per_mtok} / ${m.price.output_per_mtok} (${m.price.captured_at.slice(0, 10)})` : "—"}</td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Enable ${m.slug}`}
                    checked={m.enabled}
                    onChange={(e) =>
                      run(() => api(`/api/v1/models/${m.id}`, { method: "PATCH", body: { enabled: e.target.checked } }), "Updated.")
                    }
                  />
                </td>
                <td>
                  {m.kind === "cloud" && (
                    <form
                      className="row"
                      onSubmit={(e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        run(
                          () =>
                            api(`/api/v1/models/${m.id}/price`, {
                              method: "PUT",
                              body: {
                                input_per_mtok: Number(f.get("in")),
                                output_per_mtok: Number(f.get("out")),
                                source: f.get("source") || "admin entry",
                              },
                            }),
                          "Price snapshot recorded."
                        );
                      }}
                    >
                      <input name="in" type="number" step="any" min="0" placeholder="in $/M" aria-label="Input price per million" required style={{ width: 90 }} />
                      <input name="out" type="number" step="any" min="0" placeholder="out $/M" aria-label="Output price per million" required style={{ width: 90 }} />
                      <input name="source" type="text" placeholder="source" aria-label="Price source" style={{ width: 120 }} />
                      <button type="submit">Set price</button>
                    </form>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Add a model</h3>
      <form
        className="grid"
        onSubmit={(e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          const form = e.currentTarget;
          run(
            async () => {
              await api("/api/v1/models", {
                method: "POST",
                body: {
                  slug: f.get("slug"),
                  kind: f.get("kind"),
                  provider: f.get("provider"),
                  provider_model: f.get("provider_model") || null,
                  endpoint: f.get("endpoint"),
                  context_limit: Number(f.get("context_limit")),
                  max_output: Number(f.get("max_output")),
                },
              });
              form.reset();
            },
            "Model added."
          );
        }}
      >
        <div><label htmlFor="slug">Slug</label><input id="slug" name="slug" type="text" required /></div>
        <div><label htmlFor="kind">Kind</label><select id="kind" name="kind"><option>local</option><option>cloud</option></select></div>
        <div><label htmlFor="provider">Provider</label><input id="provider" name="provider" type="text" defaultValue="openrouter" required /></div>
        <div><label htmlFor="pm">Provider model id</label><input id="pm" name="provider_model" type="text" placeholder="Ollama tag / OpenRouter id" /></div>
        <div><label htmlFor="endpoint">Endpoint</label><input id="endpoint" name="endpoint" type="text" defaultValue="https://openrouter.ai/api/v1" required /></div>
        <div><label htmlFor="ctx">Context limit</label><input id="ctx" name="context_limit" type="number" min="1" defaultValue="8192" required /></div>
        <div><label htmlFor="mo">Max output</label><input id="mo" name="max_output" type="number" min="1" defaultValue="1024" required /></div>
        <div style={{ alignSelf: "end" }}><button className="primary" type="submit">Add model</button></div>
      </form>
    </>
  );
}

function Institutional() {
  const { data, error, reload } = useLoad("/api/v1/institutional-policy");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  if (!data) return <Status error={error} note="" />;
  const save = async (next) => {
    setErr("");
    try {
      await api("/api/v1/institutional-policy", { method: "PUT", body: next });
      setNote("Policy saved. It overrides any user consent.");
      await reload();
    } catch (e) {
      setErr(e.message);
    }
  };
  return (
    <>
      <Status error={error || err} note={note} />
      <label className="row">
        <input type="checkbox" checked={data.allow_cloud} onChange={(e) => save({ ...data, allow_cloud: e.target.checked })} />
        Allow cloud models at all
      </label>
      <fieldset>
        <legend>Forbid cloud for labels</legend>
        {["internal", "confidential"].map((label) => (
          <label key={label} className="row">
            <input
              type="checkbox"
              checked={data.forbid_labels.includes(label)}
              onChange={(e) =>
                save({
                  ...data,
                  forbid_labels: e.target.checked
                    ? [...data.forbid_labels, label]
                    : data.forbid_labels.filter((l) => l !== label),
                })
              }
            />
            {label}
          </label>
        ))}
      </fieldset>
    </>
  );
}

function Policies() {
  const { data, error, reload } = useLoad("/api/v1/policies");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const act = async (fn, msg) => {
    setErr("");
    try {
      const out = await fn();
      setNote(typeof msg === "function" ? msg(out) : msg);
      await reload();
    } catch (e) {
      setErr(e.message);
    }
  };
  return (
    <>
      <Status error={error || err} note={note} />
      <p className="muted">
        Fixed rules (version 0) always exist and are the rollback target. Learned versions are
        immutable; a new one is published every 50 scored outcomes and runs in shadow mode until
        you activate it.
      </p>
      <div className="row">
        <button className="danger" onClick={() => act(() => api("/api/v1/policies/rollback", { method: "POST" }), "Rolled back.")}>
          Roll back
        </button>
        <button onClick={() => act(() => api("/api/v1/policies/learn", { method: "POST" }), (o) => (o.published ? `Published ${o.published.version}.` : "No fresh scored outcomes."))}>
          Learn from fresh outcomes now
        </button>
        <button onClick={() => act(() => api("/api/v1/policies/check-rollback", { method: "POST" }), (o) => (o.rolled_back_reason ? `Auto-rolled back: ${o.rolled_back_reason}` : "No rollback trigger fired."))}>
          Check rollback triggers
        </button>
      </div>
      <div className="scroll-x">
        <table>
          <thead><tr><th>Version</th><th>Kind</th><th>ε</th><th>Created</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {(data || []).map((p) => (
              <tr key={p.id}>
                <td>{p.version}</td><td>{p.kind}</td><td>{p.epsilon == null ? "—" : p.epsilon.toFixed(3)}</td>
                <td>{new Date(p.created_at).toLocaleString()}</td>
                <td>{p.active ? <span className="chip public">active</span> : "inactive"}</td>
                <td>{!p.active && <button onClick={() => act(() => api(`/api/v1/policies/${p.id}/activate`, { method: "POST" }), `Activated ${p.version}.`)}>Activate</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Budgets() {
  const { data, error } = useLoad("/api/v1/admin/budgets");
  return (
    <>
      <Status error={error} note="" />
      {data && data.length === 0 && <p className="muted">No provider connections yet.</p>}
      <div className="scroll-x">
        <table>
          <thead><tr><th>Connection</th><th>Key</th><th>Monthly cap</th><th>Spent this month</th></tr></thead>
          <tbody>
            {(data || []).map((b) => (
              <tr key={b.connection_id}>
                <td>{b.label}</td><td>…{b.last4}</td>
                <td>{b.monthly_budget_usd == null ? "no cap" : `$${b.monthly_budget_usd}`}</td>
                <td>${b.month_spend_usd.toFixed(5)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Users() {
  const { data, error, reload } = useLoad("/api/v1/admin/users");
  const [err, setErr] = useState("");
  const act = async (fn) => {
    setErr("");
    try {
      await fn();
      await reload();
    } catch (e) {
      setErr(e.message);
    }
  };
  return (
    <>
      <Status error={error || err} note="" />
      <div className="scroll-x">
        <table>
          <thead><tr><th>Email</th><th>Role</th><th>Active</th></tr></thead>
          <tbody>
            {(data || []).map((u) => (
              <tr key={u.id}>
                <td>{u.email}</td>
                <td>
                  <select
                    aria-label={`Role for ${u.email}`}
                    value={u.role}
                    onChange={(e) => act(() => api(`/api/v1/admin/users/${u.id}/role`, { method: "PUT", body: { role: e.target.value } }))}
                  >
                    <option>user</option><option>rater</option><option>admin</option>
                  </select>
                </td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Active ${u.email}`}
                    checked={u.is_active}
                    onChange={(e) => act(() => api(`/api/v1/admin/users/${u.id}/active`, { method: "PUT", body: { is_active: e.target.checked } }))}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Raters() {
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [report, setReport] = useState(null);
  const act = async (fn, msg) => {
    setErr("");
    try {
      setNote(msg(await fn()));
    } catch (e) {
      setErr(e.message);
    }
  };
  return (
    <>
      <Status error={err} note={note} />
      <p className="muted">
        Enqueue a stratified set of non-sensitive answered requests, assign each to two raters,
        then review agreement (weighted κ) and source bias before pooling ratings.
      </p>
      <div className="row">
        <button onClick={() => act(() => api("/api/v1/rater/enqueue-events?limit=120", { method: "POST" }), (o) => `Queued ${o.created} item(s).`)}>Enqueue events (≤120)</button>
        <button onClick={() => act(() => api("/api/v1/rater/assign?raters_per_item=2", { method: "POST" }), (o) => `Assigned ${o.assigned_items} item(s).`)}>Assign to 2 raters</button>
        <button onClick={async () => setReport({ agreement: await api("/api/v1/rater/agreement"), bias: await api("/api/v1/rater/source-bias") })}>Show agreement report</button>
      </div>
      {report && <pre className="preview">{JSON.stringify(report, null, 2)}</pre>}
    </>
  );
}

function Retention() {
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  return (
    <>
      <Status error={err} note={note} />
      <p className="muted">Raw session content is purged after 60 minutes of inactivity (unless opted in); routing metadata after 30 days.</p>
      <button
        onClick={async () => {
          try {
            const o = await api("/api/v1/admin/retention/run", { method: "POST" });
            setNote(`Purged ${o.sessions_purged} session(s) and ${o.events_purged} old event(s).`);
          } catch (e) {
            setErr(e.message);
          }
        }}
      >
        Run retention now
      </button>
    </>
  );
}

export default function AdminPage() {
  const user = useRequireUser(["admin"]);
  const [tab, setTab] = useState(TABS[0]);
  if (!user) return <p>Loading…</p>;
  const View = { Registry, "Institutional policy": Institutional, Policies, Budgets, Users, Raters, Retention }[tab];
  return (
    <>
      <h1>Admin</h1>
      <div className="row" role="tablist" aria-label="Admin sections">
        {TABS.map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "primary" : ""} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>
      <div className="card" role="tabpanel" style={{ marginTop: "0.75rem" }}>
        <View />
      </div>
    </>
  );
}
