"use client";

import { useEffect, useRef, useState } from "react";

// Names the destination model and shows the redacted payload before any consent is granted.
export default function ConsentDialog({ request, label, onGrant, onCancel }) {
  const ref = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && request && !dialog.open) dialog.showModal();
    if (dialog && !request && dialog.open) dialog.close();
  }, [request]);

  if (!request) return null;
  return (
    <dialog ref={ref} aria-labelledby="consent-title" onClose={onCancel}>
      <h2 id="consent-title">Send this to {request.model}?</h2>
      <p>
        This request contains sensitive content or a <span className={`chip ${label}`}>{label}</span>{" "}
        label, so it stays local unless you consent. Consent applies to <strong>this exact
        payload</strong> and <strong>this model only</strong>, and expires in 60 minutes. You
        can revoke it under Settings → Privacy.
      </p>
      <p className="muted">Redacted preview of what would be sent (detected identifiers are masked):</p>
      <pre className="preview">{request.preview || "(preview unavailable)"}</pre>
      <p role="alert" className="error">{error}</p>
      <div className="row">
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            setError("");
            try {
              await onGrant(request);
            } catch (err) {
              setError(err.message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Consent and send to {request.model}
        </button>
        <button onClick={onCancel}>Keep it local</button>
      </div>
    </dialog>
  );
}
