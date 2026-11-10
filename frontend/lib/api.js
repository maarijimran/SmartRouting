// Thin API client. The access token lives in memory (and sessionStorage so a reload keeps the
// session); the refresh token is an httpOnly cookie handled by the browser. Provider API keys
// are only ever sent once, on create, and are never stored or rendered by the frontend.

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let accessToken = null;

export function getToken() {
  if (accessToken) return accessToken;
  if (typeof window !== "undefined") {
    try {
      accessToken = window.sessionStorage.getItem("sr_token");
    } catch {
      /* storage unavailable */
    }
  }
  return accessToken;
}

export function setToken(token) {
  accessToken = token;
  if (typeof window === "undefined") return;
  try {
    if (token) window.sessionStorage.setItem("sr_token", token);
    else window.sessionStorage.removeItem("sr_token");
  } catch {
    /* storage unavailable */
  }
}

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function refresh() {
  const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!response.ok) return false;
  setToken((await response.json()).access_token);
  return true;
}

function headers(extra = {}) {
  const token = getToken();
  return { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extra };
}

async function detail(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg).join("; ");
  } catch {
    /* not json */
  }
  return response.statusText || "Request failed";
}

export async function api(path, { method = "GET", body, form, retry = true } = {}) {
  const init = { method, credentials: "include", headers: headers() };
  if (form) {
    init.body = form;
  } else if (body !== undefined) {
    init.headers = headers({ "Content-Type": "application/json" });
    init.body = JSON.stringify(body);
  }
  let response = await fetch(`${API_URL}${path}`, init);
  if (response.status === 401 && retry && !path.startsWith("/api/v1/auth/")) {
    if (await refresh()) {
      init.headers = { ...init.headers, ...headers() };
      response = await fetch(`${API_URL}${path}`, init);
    }
  }
  if (!response.ok) throw new ApiError(response.status, await detail(response));
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  return type.includes("json") ? response.json() : response.text();
}

export async function downloadBlob(path, filename) {
  const response = await fetch(`${API_URL}${path}`, { headers: headers(), credentials: "include" });
  if (!response.ok) throw new ApiError(response.status, await detail(response));
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

// Server-sent events over fetch (EventSource cannot send an Authorization header).
export async function streamChat(sessionId, body, onEvent, signal) {
  const response = await fetch(`${API_URL}/api/v1/sessions/${sessionId}/chat`, {
    method: "POST",
    credentials: "include",
    headers: headers({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw new ApiError(response.status, await detail(response));
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      const event = block.match(/^event: (.*)$/m)?.[1];
      const data = block.match(/^data: (.*)$/m)?.[1];
      if (event && data) onEvent(event, JSON.parse(data));
    }
  }
}

export const REASONS = {
  local_only_mode: {
    label: "Local-only mode",
    fix: "Switch this session to Cloud-allowed to let cloud models be considered.",
  },
  consent_required: {
    label: "Consent required",
    fix: "Sensitive content or a confidential label needs your scoped consent for this model.",
  },
  no_provider_key: {
    label: "No provider key",
    fix: "Add a provider key in Settings → Keys and pick models in Settings → Models.",
  },
  over_budget: {
    label: "Over budget",
    fix: "Raise this connection's monthly cap in Settings → Keys, or wait for the next month.",
  },
  context_infeasible: {
    label: "Does not fit context",
    fix: "Shorten the question or document, or start a new session to drop old turns.",
  },
  host_unhealthy: {
    label: "Host unreachable",
    fix: "Check that Ollama (local) or the provider is reachable, or retry shortly.",
  },
  price_unknown: {
    label: "Price unknown",
    fix: "An admin must record a price for this model before it can be used.",
  },
  institutional_cloud_prohibition: {
    label: "Institutional policy",
    fix: "Your institution prohibits sending data to cloud models. Use local-only mode.",
  },
  institutional_label_prohibition: {
    label: "Institutional label rule",
    fix: "Policy forbids cloud for this label. Relabel the content only if that is accurate.",
  },
  scanner_error: {
    label: "Privacy scanner failed",
    fix: "Cloud is blocked for safety until the scanner works. Local models are unaffected.",
  },
  model_disabled: { label: "Model disabled", fix: "An admin has disabled this model." },
  policy_has_no_action: { label: "No action", fix: "No eligible model for this policy." },
};

export function reasonText(reason) {
  return REASONS[reason] || { label: reason, fix: "" };
}
