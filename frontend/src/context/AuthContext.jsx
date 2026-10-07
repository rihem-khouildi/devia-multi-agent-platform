import { createContext, useContext, useState, useEffect, useCallback } from "react"
import { api } from "../lib/api"

const AuthContext = createContext(null)

const TOKEN_KEY = "devia_auth_token"

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    setToken(null)
    setUser(null)
  }, [])

  // Fetch current user on mount / when token changes
  useEffect(() => {
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    setLoading(true)
    api.auth.me()
      .then((u) => setUser(u))
      .catch(() => {
        // Token invalid or expired — clear it
        logout()
      })
      .finally(() => setLoading(false))
  }, [token, logout])

  const login = useCallback(async (username, password) => {
    const data = await api.auth.login(username, password)
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setToken(data.access_token)
    // me() will be called via the useEffect above
  }, [])

  const register = useCallback(async (username, email, password) => {
    const data = await api.auth.register(username, email, password)
    localStorage.setItem(TOKEN_KEY, data.access_token)
    setToken(data.access_token)
  }, [])

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider")
  return ctx
}
