import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, clearToken, getToken, setOnUnauthorized, setToken } from '../lib/api';
import type { LoginResponse, Role, User } from '../lib/types';

const ROLE_RANK: Record<Role, number> = { viewer: 0, operator: 1, approver: 2, admin: 3 };

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  hasRole: (min: Role) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Bounce to login if any request 401s.
    setOnUnauthorized(() => setUser(null));

    let cancelled = false;
    if (getToken()) {
      api<User>('/api/auth/me')
        .then((u) => !cancelled && setUser(u))
        .catch(() => !cancelled && setUser(null))
        .finally(() => !cancelled && setLoading(false));
    } else {
      setLoading(false);
    }
    return () => {
      cancelled = true;
    };
  }, []);

  async function login(email: string, password: string) {
    const res = await api<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    setToken(res.access_token);
    setUser({ email: res.email, role: res.role });
  }

  function logout() {
    clearToken();
    setUser(null);
  }

  const hasRole = (min: Role) => !!user && ROLE_RANK[user.role] >= ROLE_RANK[min];

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasRole }}>
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
