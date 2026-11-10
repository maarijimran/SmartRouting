"use client";

import { useEffect, useState } from "react";
import { GroupedBars, Series } from "../../components/Charts";
import { api, downloadBlob } from "../../lib/api";
import { useRequireUser } from "../../lib/auth";

const pct = (v) => (v == null ? "—" : `${(v * 100).toFixed(0)}%`);
const ms = (v) => (v == null ? "—" : `${Math.round(v)} ms`);
const usd = (v) => (v == null ? "—" : `$${v.toFixed(5)}`);

export default function AnalyticsPage() {
  const user = useRequireUser();
  const [scope, setScope] = useState("me");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!user) return;
    setData(null);
    const q = `?scope=${scope}`;
    Promise.all([
      api(`/api/v1/analytics/summary${q}`),
      api(`/api/v1/analytics/by-model${q}`),
      api(`/api/v1/analytics/by-task${q}`),
      api(`/api/v1/analytics/cost-latency${q}`),
      api(`/api/v1/analytics/privacy${q}`),
    ])
      .then(([summary, byModel, byTask, series, privacy]) =>
        setData({ summary, byModel, byTask, series, privacy })
      )
      .catch((e) => setError(e.message));
  }, [user, scope]);

  if (!user) return <p>Loading…</p>;
  const s = data?.summary;

  return (
    <>
      <h1>Analytics</h1>
      <div className="row">
        {user.role === "admin" && (
          <>
            <label htmlFor="scope" style={{ margin: 0 }}>Scope</label>
            <select id="scope" value={scope} onChange={(e) => setScope(e.target.value)}>
              <option value="me">My requests</option>
              <option value="global">All users (admin)</option>
            </select>
            <button onClick={() => downloadBlob("/api/v1/export/events?format=csv", "events.csv")}>Export CSV</button>
            <button onClick={() => downloadBlob("/api/v1/export/events?format=json", "events.json")}>Export JSON</button>
          </>
        )}
      </div>
      <p role="alert" className="error">{error}</p>
      {!data && !error && <p>Loading…</p>}
      {data && s.requests === 0 && (
        <p className="muted">No requests yet. Ask a question in Chat and come back.</p>
      )}
      {data && s.requests > 0 && (
        <>
          <div className="tiles" aria-label="Summary">
            <div className="tile"><div className="v">{s.requests}</div><div className="k">requests</div></div>
            <div className="tile"><div className="v">{pct(s.abstention_rate)}</div><div className="k">abstained</div></div>
            <div className="tile"><div className="v">{pct(s.local_share)}</div><div className="k">answered locally</div></div>
            <div className="tile"><div className="v">{usd(s.measured.total_cost_usd)}</div><div className="k">measured cost</div></div>
            <div className="tile"><div className="v">{ms(s.measured.latency_p50_ms)}</div><div className="k">latency p50</div></div>
            <div className="tile"><div className="v">{ms(s.measured.latency_p95_ms)}</div><div className="k">latency p95</div></div>
            <div className="tile"><div className="v">{ms(s.measured.ttft_p50_ms)}</div><div className="k">TTFT p50</div></div>
            <div className="tile"><div className="v">{ms(s.routing_overhead.p50_ms)}</div><div className="k">routing overhead p50 (target &lt; 500)</div></div>
            <div className="tile"><div className="v">{s.attempt_failures}</div><div className="k">failed attempts</div></div>
            <div className="tile"><div className="v">{s.quality_mean == null ? "—" : s.quality_mean.toFixed(2)}</div><div className="k">mean quality (rated)</div></div>
          </div>

          <div className="grid" style={{ marginTop: "1rem" }}>
            <div className="card">
              <GroupedBars
                title="Mean cost per answered request, by model"
                seriesA="measured"
                seriesB="estimated"
                data={data.byModel.map((m) => ({
                  label: m.model,
                  a: m.measured_mean_cost_usd ?? 0,
                  b: m.estimated_mean_cost_usd ?? 0,
                }))}
                format={(v) => v.toFixed(5)}
              />
            </div>
            <div className="card">
              <GroupedBars
                title="Median latency by model (measured)"
                seriesA="p50 ms"
                data={data.byModel.map((m) => ({ label: m.model, a: m.measured_latency_p50_ms ?? 0 }))}
                format={(v) => `${Math.round(v)}`}
              />
            </div>
            <div className="card">
              <GroupedBars
                title="Quality by task (rated answers)"
                seriesA="mean quality"
                data={data.byTask.map((t) => ({ label: t.task, a: t.quality_mean ?? 0 }))}
                format={(v) => v.toFixed(2)}
              />
            </div>
            <div className="card">
              <Series
                title="Per-request cost: estimated vs measured"
                seriesA="estimated"
                seriesB="measured"
                points={data.series.map((p) => ({ a: p.estimated_cost_usd, b: p.measured_cost_usd }))}
              />
            </div>
          </div>

          <div className="card">
            <h2>By task</h2>
            <div className="scroll-x">
              <table>
                <thead><tr><th>Task</th><th>Requests</th><th>Abstained</th><th>Local share</th><th>Mean cost</th><th>Latency p50</th></tr></thead>
                <tbody>
                  {data.byTask.map((t) => (
                    <tr key={t.task}>
                      <td>{t.task}</td><td>{t.requests}</td><td>{t.abstained}</td>
                      <td>{pct(t.local_share)}</td><td>{usd(t.measured_mean_cost_usd)}</td><td>{ms(t.measured_latency_p50_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h2>Privacy counters</h2>
            <p>Egress blocks (outbound gate): <strong>{data.privacy.egress_blocked}</strong></p>
            <p>
              Detected entities (type: count, no text stored):{" "}
              {Object.keys(data.privacy.findings_by_type).length === 0
                ? "none"
                : Object.entries(data.privacy.findings_by_type).map(([k, v]) => `${k}: ${v}`).join(", ")}
            </p>
            <p>
              Abstention reasons:{" "}
              {Object.keys(data.privacy.abstain_reasons).length === 0
                ? "none"
                : Object.entries(data.privacy.abstain_reasons).map(([k, v]) => `${k}: ${v}`).join(", ")}
            </p>
          </div>
        </>
      )}
    </>
  );
}
