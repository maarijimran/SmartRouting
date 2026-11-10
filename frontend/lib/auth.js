"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  const load = useCallback(async () => {
    if (!getToken()) {
      // try the refresh cookie once (e.g. after the tab was closed)
      try {
        const out = await api("/api/v1/auth/refresh", { method: "POST", retry: false });
        setToken(out.access_token);
      } catch {
        setUser(null);
        setReady(true);
        return;
      }
    }
    try {
      setUser(await api("/api/v1/auth/me"));
    } catch {
      setToken(null);
      setUser(null);
    }
    setReady(true);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const login = async (email, password, path = "login") => {
    const out = await api(`/api/v1/auth/${path}`, { method: "POST", body: { email, password } });
    setToken(out.access_token);
    setUser(await api("/api/v1/auth/me"));
  };

  const logout = async () => {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* already signed out */
    }
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, ready, login, register: (e, p) => login(e, p, "register"), logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);

// Redirects to /login when signed out, and to /chat when the role is not allowed.
export function useRequireUser(roles) {
  const { user, ready } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace("/login");
    else if (roles && !roles.includes(user.role)) router.replace("/chat");
  }, [ready, user, roles, router]);
  return ready && user && (!roles || roles.includes(user.role)) ? user : null;
}
