// The single place the client talks to the server.
//
// Every call goes through `request`, so authentication, error shape and JSON
// handling are decided once. Components never touch fetch directly: a
// component that did would have its own idea of what an error is, and the
// 401-means-signed-out rule would hold only where someone remembered it.

export class ApiError extends Error {
  constructor(status, detail, body) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }

  // A session that expired or was cleared server-side. The app watches for
  // this to fall back to the login screen rather than showing an error the
  // user can do nothing about.
  get isUnauthorized() {
    return this.status === 401;
  }
}

// FastAPI puts the message in `detail`, which is a string for the errors we
// raise by hand and a list of field objects for a validation failure. Both
// have to become one readable line, or a 422 renders as "[object Object]".
function messageFrom(status, body) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = (d.loc ?? []).filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return `Uventet feil (${status})`;
}

async function request(path, { method = "GET", body, form, signal } = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      // The session cookie is httpOnly and same-origin; `same-origin`
      // credentials is what makes the browser attach it. Without it every
      // request after login is a 401.
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
      signal,
    });
  } catch (cause) {
    if (cause?.name === "AbortError") throw cause;
    // A dead server, a dropped tailnet, aeroplane mode. Distinguished from an
    // HTTP error because the advice differs: retry versus fix the request.
    throw new ApiError(0, "Får ikke kontakt med serveren.", null);
  }

  if (response.status === 204) return null;

  let parsed = null;
  const text = await response.text();
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, messageFrom(response.status, parsed), parsed);
  }
  return parsed;
}

const query = (params) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null) search.set(key, String(value));
  }
  const string = search.toString();
  return string ? `?${string}` : "";
};

export const api = {
  auth: {
    status: () => request("/auth/status"),
    setPasscode: (passcode) => request("/auth/passcode", { method: "POST", body: { passcode } }),
    login: (passcode) => request("/auth/login", { method: "POST", body: { passcode } }),
    logout: () => request("/auth/logout", { method: "POST" }),
    changePasscode: (currentPasscode, newPasscode) =>
      request("/auth/passcode", {
        method: "PUT",
        body: { current_passcode: currentPasscode, new_passcode: newPasscode },
      }),
  },

  budget: {
    get: (date) => request(`/budget${query({ date })}`),
    config: (date) => request(`/budget/config${query({ date })}`),
    saveConfig: (changes) => request("/budget/config", { method: "PUT", body: changes }),
  },

  transactions: {
    list: (params) => request(`/transactions${query(params)}`),
    get: (id) => request(`/transactions/${id}`),
    create: (row) => request("/transactions", { method: "POST", body: row }),
    patch: (id, changes) => request(`/transactions/${id}`, { method: "PATCH", body: changes }),
  },

  categories: {
    list: () => request("/categories"),
    setTreatment: (name, treatment) =>
      request(`/categories/${encodeURIComponent(name)}`, {
        method: "PATCH",
        body: { budget_treatment: treatment },
      }),
  },

  accounts: {
    list: () => request("/accounts"),
  },

  reimbursements: {
    list: () => request("/reimbursements"),
    settle: (id) => request(`/reimbursements/${id}/settle`, { method: "POST", body: {} }),
  },

  imports: {
    // multipart, so the body is a FormData and the Content-Type header is
    // left for the browser to set — it has to add the multipart boundary.
    preview: (file, account) => request("/imports/preview", { method: "POST", form: formData(file, account) }),
    commit: (file, account) => request("/imports", { method: "POST", form: formData(file, account) }),
  },
};

function formData(file, account) {
  const data = new FormData();
  data.append("file", file);
  data.append("account", account);
  return data;
}
