import { useState, useRef, useEffect } from 'react'
import { KeyRound, Users, LogOut } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

function UserMenu({ onChangePassword, onManageUsers }) {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef(null)
  const { user, isAdmin, logout, isreadonly } = useAuth()

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const formatDate = (dateStr) => {
    if (!dateStr) return '未知'
    try {
      const date = new Date(dateStr)
      // 检查日期是否有效
      if (isNaN(date.getTime())) return '未知'
      
      // 确保显示为中国时区时间 (GMT+8)
      const options = {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        timeZone: 'Asia/Shanghai'  // 明确指定中国时区
      }
      
      return date.toLocaleString('zh-CN', options)
    } catch (error) {
      console.error('日期格式化错误:', error)
      return '未知'
    }
  }

  return (
    <div className="user-menu" ref={menuRef}>
      <button 
        className="user-menu-trigger"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="user-avatar">
          {user?.full_name?.[0] || user?.username?.[0] || '?'}
        </span>
        <span className="user-name">{user?.full_name || user?.username}</span>
        <span className="dropdown-arrow">▼</span>
      </button>

      {isOpen && (
        <div className="user-menu-dropdown">
          <div className="user-info-section">
            <div className="user-info-item">
              <span className="label">用户名:</span>
              <span className="value">{user?.username}</span>
            </div>
            <div className="user-info-item">
              <span className="label">姓名:</span>
              <span className="value">{user?.full_name || '-'}</span>
            </div>
            <div className="user-info-item">
              <span className="label">邮箱:</span>
              <span className="value">{user?.email || '-'}</span>
            </div>
            <div className="user-info-item">
              <span className="label">角色:</span>
              <span className={`value role-badge ${user?.role}`}>
                {user?.role === 'admin' ? '管理员' : user.role === 'readonly' ? '只读用户': 'MIS'}
              </span>
            </div>
            <div className="user-info-item">
              <span className="label">上次登录:</span>
              <span className="value">{formatDate(user?.last_login)}</span>
            </div>
          </div>

          <div className="user-menu-divider"></div>

          <div className="user-menu-actions">
            <button 
              className="menu-action-btn"
              onClick={() => {
                setIsOpen(false)
                onChangePassword?.()
              }}
            >
              <KeyRound size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} /> 修改密码
            </button>
            
            {isAdmin && (
              <button 
                className="menu-action-btn"
                onClick={() => {
                  setIsOpen(false)
                  onManageUsers?.()
                }}
              >
                <Users size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} /> 用户管理
              </button>
            )}
            
            <button 
              className="menu-action-btn logout-btn"
              onClick={() => {
                setIsOpen(false)
                logout()
              }}
            >
              <LogOut size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} /> 退出登录
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default UserMenu
