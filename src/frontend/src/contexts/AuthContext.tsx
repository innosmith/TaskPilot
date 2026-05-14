import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import { api, getToken, setToken, clearToken, tryRefreshToken } from '../api/client';
import type { LoginRequest, LoginResponse, UserProfile, UserRole } from '../types';

interface AuthContextValue {
  token: string | null;
  isAuthenticated: boolean;
  user: UserProfile | null;
  role: UserRole | null;
  isOwner: boolean;
  login: (credentials: LoginRequest) => Promise<LoginResponse>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken());
  const [user, setUser] = useState<UserProfile | null>(null);

  const fetchProfile = useCallback(async () => {
    try {
      const profile = await api.get<UserProfile>('/api/auth/me');
      setUser(profile);
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    const stored = getToken();
    if (stored !== token) {
      setTokenState(stored);
    }
  }, [token]);

  const refreshAttempted = useRef(false);

  useEffect(() => {
    if (token) {
      fetchProfile();
    } else if (!refreshAttempted.current) {
      refreshAttempted.current = true;
      tryRefreshToken().then((ok) => {
        if (ok) {
          const fresh = getToken();
          if (fresh) setTokenState(fresh);
        }
      });
    } else {
      setUser(null);
    }
  }, [token, fetchProfile]);

  const login = useCallback(async (credentials: LoginRequest): Promise<LoginResponse> => {
    const data = await api.post<LoginResponse>(
      '/api/auth/login',
      credentials,
    );
    if (data.requires_mfa) {
      return data;
    }
    setToken(data.access_token);
    setTokenState(data.access_token);
    return data;
  }, []);

  const logout = useCallback(() => {
    clearToken();
    setTokenState(null);
    setUser(null);
  }, []);

  const refreshProfile = useCallback(async () => {
    await fetchProfile();
  }, [fetchProfile]);

  return (
    <AuthContext.Provider
      value={{
        token,
        isAuthenticated: !!token,
        user,
        role: user?.role ?? null,
        isOwner: user?.role === 'owner',
        login,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
