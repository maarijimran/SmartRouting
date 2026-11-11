"use client";

import { useEffect, useRef, useState } from "react";
import { entityLabel, scopeLabel } from "../lib/api";

// Shown before routing when the request contains sensitive content (detected identifiers or a
// confidential/internal label). The user sees what was found and decides: answer locally, or
// grant scoped consent and send this exact payload to one cloud model. Nothing has been sent.
export default function SensitiveReview({ review, onLocal, onCloud, onCancel }) {
  const ref = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && review && !dialog.open) dialog.showModal();
    if (dialog && !review && dialog.open) dialog.close();
  }, [review]);

  if (!review) return null;
  const findings = review.findings || [];
  const options = review.cloud_options || [];
  const preview = options.find((o) => o.preview)?.preview;

  async function run(action) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog ref={ref} aria-labelledby="review-title" onClose={onCancel}>
      <h2 id="review-title">Sensitive content found — where should this go?</h2>
      <p>
        Nothing has been sent yet. Content label:{" "}
        <span className={`chip ${review.label}`}>{review.label}</span>
      </p>

      {findings.length > 0 ? (
        <table>
          <caption className="muted">What the privacy scan found (local scan, nothing stored)</caption>
          <thead>
            <tr><th scope="col">Type</th><th scope="col">Where</th><th scope="col">Count</th></tr>
          </thead>
          <tbody>
            {findings.map((f) => (
              <tr key={`${f.scope}-${f.entity_type}`}>
                <td>{entityLabel(f.entity_type)}</td>
                <td>{scopeLabel(f.scope)}</td>
                <td>{f.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>No identifiers were detected, but the <strong>{review.label}</strong> label requires your decision.</p>
      )}

      <p className="muted">Redacted preview of what a cloud model would receive (detected items masked):</p>
      <pre className="preview">{preview || "(preview unavailable)"}</pre>
      <p className="muted">
        Cloud consent applies to <strong>this exact payload</strong> and <strong>one model</strong>,
        expires in 60 minutes, and can be revoked under Settings → Privacy.
      </p>
      <p role="alert" className="error">{error}</p>

      <div className="row">
        <button
          className="primary"
          disabled={busy || !review.local_available}
          title={review.local_available ? "" : "No local model is reachable right now"}
          onClick={() => run(onLocal)}
        >
          Answer locally{review.local_models?.length ? ` (${review.local_models.join(", ")})` : ""}
        </button>
        {options.map((o) => (
          <button key={o.model} disabled={busy} onClick={() => run(() => onCloud(o))}>
            Send to cloud: {o.model}{o.tier ? ` (${o.tier})` : ""}
          </button>
        ))}
        <button disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
      {!review.local_available && (
        <p className="muted">No local model is reachable, so only cloud (with consent) can answer.</p>
      )}
    </dialog>
  );
}
