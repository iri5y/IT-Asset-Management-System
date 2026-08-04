import { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''

// 无操作超时时间：30 分钟（毫秒）
const IDLE_TIMEOUT_MS = 30 * 60 * 1000
// 认证初始化不能无限等待后端，否则首屏会永久停留在加载状态
const AUTH_REQUEST_TIMEOUT_MS = 10 * 1000

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [passwordExpired, setPasswordExpired] = useState(false)
  const [passwordRemind, setPasswordRemind] = useState(false)
  const [mustChangePassword, setMustChangePassword] = useState(false)

  // 用 ref 持有 logout，避免 useEffect 依赖循环
  const logoutRef = useRef(null)
  // 超时计时器 ref
  const idleTimerRef = useRef(null)

  // ── 清除登录状态（内部复用）──────────────────────────────
  const clearAuth = useCallback(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
    setPasswordExpired(false)
    setPasswordRemind(false)
    setMustChangePassword(false)
  }, [])

  // ── 重置空闲计时器 ────────────────────────────────────────
  const resetIdleTimer = useCallback(() => {
    if (!logoutRef.current) return
    clearTimeout(idleTimerRef.current)
    idleTimerRef.current = setTimeout(() => {
      // 只有已登录时才触发超时登出
      if (localStorage.getItem('access_token')) {
        logoutRef.current()
      }
    }, IDLE_TIMEOUT_MS)
  }, [])

  // ── 初始化：用 localStorage 中的 token 向后端主动校验并恢复登录状态 ──
  useEffect(() => {
    const initAuth = async () => {
      try {
        const token = localStorage.getItem('access_token')
        if (!token) {
          setLoading(false)
          return
        }

        // 先做本地格式与过期检查，避免不必要的网络请求
        let payload
        try {
          payload = JSON.parse(atob(token.split('.')[1]))
        } catch {
          // token 格式损坏，直接清除
          clearAuth()
          setLoading(false)
          return
        }

        const now = Date.now() / 1000
        if (payload.exp && payload.exp < now) {
          // access token 本地判断已过期，尝试用 refresh token 续期
          const refreshToken = localStorage.getItem('refresh_token')
          if (refreshToken) {
            try {
              const res = await axios.post(
                `${API_URL}/auth/refresh`,
                { refresh_token: refreshToken },
                { timeout: AUTH_REQUEST_TIMEOUT_MS },
              )
              const { access_token, user: userData, password_expired, password_remind, must_change_password } = res.data
              localStorage.setItem('access_token', access_token)
              setUser(userData)
              setPasswordExpired(password_expired || false)
              setPasswordRemind(password_remind || false)
              setMustChangePassword(must_change_password || false)
            } catch {
              // refresh token 也失效，清除登录
              clearAuth()
            }
          } else {
            clearAuth()
          }
          setLoading(false)
          return
        }

        // token 本地未过期，向后端主动校验（/auth/me）
        // 这一步确保 token 没有被服务端主动吊销
        try {
          const res = await axios.get(`${API_URL}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
            timeout: AUTH_REQUEST_TIMEOUT_MS,
          })
          // 后端校验通过，恢复用户状态
          setUser(res.data)
        } catch (err) {
          if (err.response?.status === 401) {
            // 后端明确返回 401：token 已失效（被吊销或服务端密钥变更）
            // 必须清除本地缓存，强制重新登录
            clearAuth()
          }
          // 其他错误（网络超时、后端未启动等）：
          // 不清除登录状态，保留 token，等用户操作时再由 axios 拦截器处理
          // 这样避免后端短暂不可用时把用户踢出
        }
      } catch (error) {
        console.error('认证初始化失败:', error)
        // 未预期的异常也不清除登录，避免误伤
      } finally {
        setLoading(false)
      }
    }

    initAuth()
  }, [clearAuth])

  // ── 配置 axios 拦截器 ─────────────────────────────────────
  useEffect(() => {
    const requestInterceptor = axios.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('access_token')
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => Promise.reject(error)
    )

    const responseInterceptor = axios.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          clearAuth()
        }
        return Promise.reject(error)
      }
    )

    return () => {
      axios.interceptors.request.eject(requestInterceptor)
      axios.interceptors.response.eject(responseInterceptor)
    }
  }, [clearAuth])

  // ── 全局空闲超时监听 ──────────────────────────────────────
  // 每次渲染都更新 ref，确保计时器回调拿到最新的 clearAuth
  useEffect(() => {
    logoutRef.current = () => {
      clearAuth()
      clearTimeout(idleTimerRef.current)
    }
  })

  useEffect(() => {
    // 只有用户已登录时才挂载监听器和启动计时器
    if (!user) {
      clearTimeout(idleTimerRef.current)
      return
    }

    const EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'click']
    const handleActivity = () => resetIdleTimer()

    EVENTS.forEach(evt => window.addEventListener(evt, handleActivity, { passive: true }))

    // 登录后立即启动第一个计时周期
    resetIdleTimer()

    return () => {
      EVENTS.forEach(evt => window.removeEventListener(evt, handleActivity))
      clearTimeout(idleTimerRef.current)
    }
  }, [user, resetIdleTimer])

  // ── 登录 ──────────────────────────────────────────────────
  const login = async (username, password) => {
    const response = await axios.post(`${API_URL}/auth/login`, { username, password })
    const { access_token, refresh_token, user: userData, password_expired, password_remind, must_change_password } = response.data

    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)
    setUser(userData)
    setPasswordExpired(password_expired || false)
    setPasswordRemind(password_remind || false)
    setMustChangePassword(must_change_password || false)

    // 计时器由 user 状态变化的 useEffect 自动启动，无需手动调用

    return { user: userData, password_expired, password_remind, must_change_password }
  }

  // ── 登出 ──────────────────────────────────────────────────
  const logout = useCallback(() => {
    clearAuth()
    clearTimeout(idleTimerRef.current)
  }, [clearAuth])

  const changePassword = async (oldPassword, newPassword) => {
    await axios.put(`${API_URL}/auth/change-password`, {
      old_password: oldPassword,
      new_password: newPassword,
    })
    setPasswordExpired(false)
    setPasswordRemind(false)
    setMustChangePassword(false)
    if (user) {
      setUser({ ...user, must_change_password: false })
    }
  }

  const dismissPasswordRemind = () => {
    setPasswordRemind(false)
  }

  const isAdmin = user?.role === 'admin'
  const isReadOnly = user?.role === 'readonly'

  const value = {
    user,
    loading,
    passwordExpired,
    passwordRemind,
    mustChangePassword,
    isAdmin,
    isReadOnly,
    login,
    logout,
    changePassword,
    dismissPasswordRemind,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}