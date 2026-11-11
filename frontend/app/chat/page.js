"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import ConsentDialog from "../../components/ConsentDialog";
import FeedbackWidget from "../../components/FeedbackWidget";
import RoutePanel from "../../components/RoutePanel";
import SensitiveReview from "../../components/SensitiveReview";
import { api, entityLabel, streamChat } from "../../lib/api";
import { useRequireUser } from "../../lib/auth";

const LABELS = ["public", "internal", "confidential"];
const COST_PREFS = [
  ["lowest", "Lowest cost"],
  ["balanced", "Balanced"],
  ["best", "Best quality"],
];

function liveToRoute(live) {
  if (!live) return null;
  return { ...live.route, evidence: live.evidence, compression: live.compression };
}

export default function ChatPage() {
  const user = useRequireUser();
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [session, setSession] = useState(null);
  const [docs, setDocs] = useState([]);
  const [messages, setMessages] = useState([]);
  const [live, setLive] = useState(null); // in-flight or abstained turn: {prompt, content, route, ...}
  const [prompt, setPrompt] = useState("");
  const [costPref, setCostPref] = useState("balanced");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [consent, setConsent] = useState(null);
  const [review, setReview] = useState(null); // sensitive-content review awaiting the user's choice
  const [now, setNow] = useState(Date.now());
  const abortRef = useRef(null);
  const fileRef = useRef(null);

  const loadSessions = useCallback(async () => {
    const list = await api("/api/v1/sessions");
    setSessions(list);
    return list;
  }, []);

  const loadSession = useCallback(async (id) => {
    const [msgs, documents, list] = await Promise.all([
      api(`/api/v1/sessions/${id}/messages`),
      api(`/api/v1/sessions/${id}/documents`),
      api("/api/v1/sessions"),
    ]);
    setMessages(msgs);
    setDocs(documents);
    setSessions(list);
    setSession(list.find((s) => s.id === id) || null);
  }, []);

  useEffect(() => {
    if (!user) return;
    loadSessions()
      .then((list) => list[0] && setActiveId(list[0].id))
      .catch((e) => setError(e.message));
  }, [user, loadSessions]);

  useEffect(() => {
    if (activeId) {
      setLive(null);
      loadSession(activeId).catch((e) => setError(e.message));
    }
  }, [activeId, loadSession]);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);

  if (!user) return <p>Loading…</p>;

  async function newSession() {
    setError("");
    const created = await api("/api/v1/sessions", { method: "POST" });
    let defaults = {};
    try {
      defaults = JSON.parse(window.localStorage.getItem("sr_defaults") || "{}");
    } catch {
      /* ignore */
    }
    if (defaults.mode || defaults.persist) {
      await api(`/api/v1/sessions/${created.id}`, {
        method: "PATCH",
        body: { ...(defaults.mode ? { mode: defaults.mode } : {}), persist_opt_in: !!defaults.persist },
      });
    }
    await loadSessions();
    setActiveId(created.id);
  }

  async function patchSession(changes) {
    const previous = session;
    setSession({ ...session, ...changes }); // optimistic: the privacy state reacts immediately
    try {
      setSession(await api(`/api/v1/sessions/${session.id}`, { method: "PATCH", body: changes }));
    } catch (e) {
      setSession(previous);
      setError(e.message);
    }
  }

  async function upload(event) {
    const file = event.target.files?.[0];
    if (!file || !session) return;
    setError("");
    const form = new FormData();
    form.append("file", file);
    try {
      await api(`/api/v1/sessions/${session.id}/documents`, { method: "POST", form });
      setDocs(await api(`/api/v1/sessions/${session.id}/documents`));
    } catch (e) {
      setError(e.message);
    }
    if (fileRef.current) fileRef.current.value = "";
  }

  async function setDocLabel(doc, label) {
    await api(`/api/v1/documents/${doc.id}`, { method: "PATCH", body: { label } });
    setDocs(await api(`/api/v1/sessions/${session.id}/documents`));
  }

  async function removeDoc(doc) {
    await api(`/api/v1/documents/${doc.id}`, { method: "DELETE" });
    setDocs(await api(`/api/v1/sessions/${session.id}/documents`));
  }

  // `choice` answers a sensitive-content review: "local" | "cloud" | undefined (not asked yet)
  async function send(text, choice) {
    if (!session || !text.trim() || busy) return;
    setBusy(true);
    setError("");
    const state = { prompt: text, content: "", route: { status: "running" }, evidence: [], compression: null };
    setLive({ ...state });
    const controller = new AbortController();
    abortRef.current = controller;
    const update = (patch) => {
      Object.assign(state, patch);
      setLive({ ...state });
    };
    try {
      await streamChat(
        session.id,
        { prompt: text, cost_preference: costPref, ...(choice ? { sensitive_choice: choice } : {}) },
        (name, data) => {
          if (name === "context") update({ evidence: data.evidence });
          else if (name === "review") {
            update({ route: null, review: data, abstained: true });
            setReview(data);
          }
          else if (name === "compression_notice") update({ compression: data });
          else if (name === "route")
            update({
              route: {
                status: "running",
                model: data.model,
                reason: data.reason,
                rule_id: data.rule_id,
                policy: data.policy,
                policy_version: data.policy_version,
                probability: data.probability,
                eligible: data.eligible,
                removed: data.removed,
                shadow: data.shadow,
                routing_latency_ms: data.routing_latency_ms,
                estimated: {
                  input_tokens: data.estimated_input_tokens,
                  output_tokens: data.estimated_output_tokens,
                  cost_usd: data.estimated_cost_usd,
                  latency_ms: data.estimated_latency_ms,
                },
                measured: {},
                attempts: [],
              },
            });
          else if (name === "token") update({ content: state.content + data.text });
          else if (name === "done")
            update({
              route: {
                ...state.route,
                status: "succeeded",
                model: data.model,
                event_id: data.event_id,
                measured: {
                  input_tokens: data.input_tokens,
                  output_tokens: data.output_tokens,
                  cost_usd: data.measured_cost_usd,
                  latency_ms: data.generation_latency_ms,
                  ttft_ms: data.ttft_ms,
                },
                attempts: [...(data.failures || []), { model: data.model, status: "ok" }],
              },
            });
          else if (name === "abstain")
            update({
              route: {
                status: "abstained",
                removed: data.removed,
                consent_needed: data.consent_needed,
                routing_latency_ms: data.routing_latency_ms,
                event_id: data.event_id,
              },
              abstained: true,
            });
          else if (name === "error")
            update({
              route: { ...state.route, status: "failed", attempts: data.failures, event_id: data.event_id },
              failed: data.suggestion,
            });
        },
        controller.signal
      );
      setPrompt("");
      if (!state.abstained) {
        await loadSession(session.id);
        setLive(null);
      } else {
        await loadSessions();
      }
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  async function grantConsent(request) {
    await api("/api/v1/consents", {
      method: "POST",
      body: {
        session_id: session.id,
        destination_model_id: request.model,
        payload_hash: request.payload_hash,
        expires_minutes: 60,
      },
    });
    setConsent(null);
    // identical payload, so the scoped consent now applies
    await send(live?.prompt || prompt, "cloud");
  }

  async function reviewChooseLocal() {
    setReview(null);
    await send(live?.prompt || prompt, "local");
  }

  async function reviewChooseCloud(option) {
    await api("/api/v1/consents", {
      method: "POST",
      body: {
        session_id: session.id,
        destination_model_id: option.model,
        payload_hash: option.payload_hash,
        expires_minutes: 60,
      },
    });
    setReview(null);
    await send(live?.prompt || prompt, "cloud");
  }

  const expires = session ? new Date(session.expires_at).getTime() : 0;
  const minutesLeft = Math.round((expires - now) / 60000);
  const cloud = session?.mode === "cloud_allowed";
  const fileInputId = "doc-upload";

  return (
    <div className="chat-layout">
      <aside className="sessions" aria-label="Sessions">
        <button className="primary" onClick={newSession}>+ New session</button>
        {sessions.length === 0 && <p className="muted">No sessions yet. Create one to start.</p>}
        {sessions.map((s, i) => (
          <button key={s.id} aria-current={s.id === activeId} onClick={() => setActiveId(s.id)}>
            Session {sessions.length - i} <span className={`chip ${s.label}`}>{s.label}</span>
            <br />
            <span className="muted">{s.mode === "local_only" ? "local-only" : "cloud allowed"}</span>
          </button>
        ))}
      </aside>

      <section aria-label="Conversation">
        {!session && <p className="muted">Create or select a session to begin.</p>}
        {session && (
          <>
            <div className="privacy-bar" role="region" aria-label="Privacy state">
              <span className="state">
                {cloud ? "☁ Cloud allowed" : "🔒 Local-only"}
              </span>
              <span className={`chip ${session.label}`}>label: {session.label}</span>
              <label className="row" style={{ margin: 0 }}>
                <input
                  type="checkbox"
                  checked={cloud}
                  onChange={(e) => patchSession({ mode: e.target.checked ? "cloud_allowed" : "local_only" })}
                />
                Allow cloud models
              </label>
              <label className="row" style={{ margin: 0 }}>
                Session label
                <select
                  value={session.label}
                  onChange={(e) => patchSession({ label: e.target.value })}
                  aria-label="Session label"
                >
                  {LABELS.map((l) => <option key={l}>{l}</option>)}
                </select>
              </label>
              <label className="row" style={{ margin: 0 }}>
                <input
                  type="checkbox"
                  checked={session.persist_opt_in}
                  onChange={(e) => patchSession({ persist_opt_in: e.target.checked })}
                />
                Keep history (opt-in)
              </label>
            </div>

            {!session.persist_opt_in && minutesLeft <= 10 && (
              <div className="banner" role="status">
                {minutesLeft <= 0
                  ? "This session has expired; its content will be purged. Start a new session."
                  : `This session's content is deleted after inactivity — about ${minutesLeft} min left.`}
              </div>
            )}

            <div className="card">
              <div className="row">
                <label htmlFor={fileInputId} style={{ margin: 0 }}>Upload document (PDF or TXT)</label>
                <input id={fileInputId} ref={fileRef} type="file" accept=".pdf,.txt,application/pdf,text/plain" onChange={upload} />
              </div>
              {docs.length === 0 ? (
                <p className="muted">No documents. Questions will be answered without evidence.</p>
              ) : (
                <ul>
                  {docs.map((d) => (
                    <li key={d.id} className="row">
                      {d.filename} · {d.pages} page(s)
                      <select
                        aria-label={`Label for ${d.filename}`}
                        value={d.label}
                        onChange={(e) => setDocLabel(d, e.target.value)}
                      >
                        {LABELS.map((l) => <option key={l}>{l}</option>)}
                      </select>
                      <button className="danger" onClick={() => removeDoc(d)}>Remove</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="messages" aria-live="polite">
              {messages.length === 0 && !live && (
                <p className="muted">Ask a question about your document, or anything else.</p>
              )}
              {messages.map((m) => (
                <div key={m.id} className={`msg ${m.role}`}>
                  <div className="who">{m.role}</div>
                  {m.content}
                  {m.role === "assistant" && m.route && <RoutePanel route={m.route} />}
                  {m.role === "assistant" && m.event_id && <FeedbackWidget eventId={m.event_id} />}
                </div>
              ))}
              {live && (
                <>
                  <div className="msg user"><div className="who">user</div>{live.prompt}</div>
                  <div className="msg assistant">
                    <div className="who">assistant</div>
                    {live.content || (busy ? "…" : "")}
                    {live.review ? (
                      <div className="card" role="status">
                        <p>
                          <strong>Waiting for your decision.</strong> Sensitive content was found
                          {live.review.findings?.length
                            ? `: ${live.review.findings
                                .map((f) => `${entityLabel(f.entity_type)} ×${f.count}`)
                                .join(", ")}`
                            : ` (label: ${live.review.label})`}
                          . Nothing has been sent.
                        </p>
                        <button onClick={() => setReview(live.review)}>Review and choose…</button>
                      </div>
                    ) : (
                      <RoutePanel route={liveToRoute(live)} onConsent={(c) => setConsent(c)} />
                    )}
                    {live.failed && <p className="error">{live.failed}</p>}
                    {live.route?.event_id && live.route.status === "succeeded" && (
                      <FeedbackWidget eventId={live.route.event_id} />
                    )}
                  </div>
                </>
              )}
            </div>

            <p role="alert" className="error">{error}</p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(prompt);
              }}
            >
              <label htmlFor="prompt">Your question</label>
              <textarea
                id="prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    send(prompt);
                  }
                }}
              />
              <label htmlFor="costpref">
                Cost preference: {COST_PREFS.find((c) => c[0] === costPref)[1]}
              </label>
              <input
                id="costpref"
                type="range"
                min="0"
                max="2"
                step="1"
                value={COST_PREFS.findIndex((c) => c[0] === costPref)}
                onChange={(e) => setCostPref(COST_PREFS[Number(e.target.value)][0])}
                aria-valuetext={COST_PREFS.find((c) => c[0] === costPref)[1]}
              />
              <div className="row" style={{ marginTop: "0.5rem" }}>
                <button className="primary" type="submit" disabled={busy || !prompt.trim()}>
                  {busy ? "Working…" : "Send (Ctrl+Enter)"}
                </button>
                {busy && <button type="button" onClick={() => abortRef.current?.abort()}>Stop</button>}
              </div>
            </form>
          </>
        )}
      </section>

      <ConsentDialog
        request={consent}
        label={session?.label}
        onGrant={grantConsent}
        onCancel={() => setConsent(null)}
      />
      <SensitiveReview
        review={review}
        onLocal={reviewChooseLocal}
        onCloud={reviewChooseCloud}
        onCancel={() => setReview(null)}
      />
    </div>
  );
}
