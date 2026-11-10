"use client";

import { reasonText } from "../lib/api";

const fmtMs = (v) => (v == null ? "—" : `${Math.round(v)} ms`);
const fmtUsd = (v) => (v == null ? "—" : `$${Number(v).toFixed(6)}`);
const fmtN = (v) => (v == null ? "—" : String(v));

// `route` is a normalised object (live SSE or stored event): estimated and measured values are
// shown in separate columns and are never mixed.
export default function RoutePanel({ route, onConsent }) {
  if (!route) return null;
  const abstained = route.status === "abstained";
  return (
    <details className="route" open={abstained || route.status === "failed"}>
      <summary>
        {abstained
          ? "Blocked — no eligible model"
          : `Route: ${route.model || "—"} · ${route.status}` +
            (route.measured?.latency_ms != null
              ? ` · ${fmtUsd(route.measured.cost_usd)} · ${fmtMs(route.measured.latency_ms)}`
              : "")}
      </summary>

      {abstained && (
        <>
          <p>Every model was ruled out. Nothing was sent to the cloud.</p>
          <ul className="removed">
            {(route.removed || []).map((r, i) => {
              const info = reasonText(r.reason);
              return (
                <li key={i}>
                  <strong>{r.model}</strong>: {info.label}. {info.fix}
                </li>
              );
            })}
          </ul>
          {(route.consent_needed || []).map((c) => (
            <div key={c.model}>
              <button onClick={() => onConsent?.(c)}>
                Review &amp; consent to send to {c.model}…
              </button>
            </div>
          ))}
        </>
      )}

      {!abstained && (
        <>
          <p>
            <strong>Why:</strong> {route.reason || "—"}{" "}
            <span className="chip">{route.rule_id || route.policy}</span>{" "}
            <span className="muted">
              policy {route.policy} v{route.policy_version}
              {route.probability != null && ` · P(action)=${Number(route.probability).toFixed(3)}`}
            </span>
          </p>
          {route.shadow && (
            <p className="muted">
              Shadow policy ({route.shadow.policy} {route.shadow.version}) would have chosen{" "}
              <strong>{route.shadow.action}</strong>; it did not serve this request.
            </p>
          )}
          <div className="scroll-x">
            <table>
              <thead>
                <tr><th></th><th>Estimated (before sending)</th><th>Measured (after)</th></tr>
              </thead>
              <tbody>
                <tr><th>Input tokens</th><td>{fmtN(route.estimated?.input_tokens)}</td><td>{fmtN(route.measured?.input_tokens)}</td></tr>
                <tr><th>Output tokens</th><td>{fmtN(route.estimated?.output_tokens)} (reserved)</td><td>{fmtN(route.measured?.output_tokens)}</td></tr>
                <tr><th>Cost</th><td>{fmtUsd(route.estimated?.cost_usd)}</td><td>{fmtUsd(route.measured?.cost_usd)}</td></tr>
                <tr><th>Latency</th><td>{fmtMs(route.estimated?.latency_ms)}</td><td>{fmtMs(route.measured?.latency_ms)}</td></tr>
                <tr><th>Time to first token</th><td>—</td><td>{fmtMs(route.measured?.ttft_ms)}</td></tr>
                <tr>
                  <th>Routing overhead</th>
                  <td colSpan={2}>
                    {fmtMs(route.routing_latency_ms)} (target &lt; 500 ms)
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}

      {(route.eligible || []).length > 0 && (
        <p><strong>Eligible:</strong> {route.eligible.join(", ")}</p>
      )}
      {!abstained && (route.removed || []).length > 0 && (
        <>
          <strong>Removed:</strong>
          <ul className="removed">
            {route.removed.map((r, i) => (
              <li key={i}>{r.model}: {reasonText(r.reason).label}</li>
            ))}
          </ul>
        </>
      )}
      {route.compression && (
        <p className="muted">
          Compression notice: {route.compression.compressed_turns} older turn(s) summarised
          locally ({route.compression.label}).
        </p>
      )}
      {(route.evidence || []).length > 0 && (
        <p className="muted">
          Sources:{" "}
          {route.evidence.map((e) => `p.${e.page} (score ${e.score})`).join(", ")}
        </p>
      )}
      {(route.attempts || []).length > 1 && (
        <p>
          <strong>Retry trail:</strong>{" "}
          {route.attempts.map((a) => `${a.model} → ${a.status}`).join(" ▸ ")}
        </p>
      )}
    </details>
  );
}
