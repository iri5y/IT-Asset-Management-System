import { useState, useEffect, useMemo } from 'react'
import axios from 'axios'
import { AlertTriangle, Eye, EyeOff } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

const isPasswordExpired = (user) => {
  if (!user.password_changed_at) return true
  if (user.role === 'admin') return false
  const changedAt = new Date(user.password_changed_at)
  const now = new Date()
  const daysDiff = Math.floor((now - changedAt) / (1000 * 60 * 60 * 24))
  return daysDiff >= 90
}

const isPasswordExpiringSoon = (user) => {
  if (!user.password_changed_at) return false
  if (user.role === 'admin') return false
  const changedAt = new Date(user.password_changed_at)
  const now = new Date()
  const daysDiff = Math.floor((now - changedAt) / (1000 * 60 * 60 * 24))
  return daysDiff >= 80 && daysDiff < 90
}

function UserManagement({ onClose }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showResetPasswordModal, setShowResetPasswordModal] = useState(false)
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [pendingAction, setPendingAction] = useState(null)
  const [selectedUser, setSelectedUser] = useState(null)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  
  const [searchText, setSearchText] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [passwordStatusFilter, setPasswordStatusFilter] = useState('')

  useEffect(() => {
    fetchUsers()
  }, [])

  const fetchUsers = async () => {
    try {
      setLoading(true)
      setError('')
      const response = await axios.get(`${API_URL}/auth/users`)
      setUsers(response.data)
    } catch (err) {
      console.error('Failed to fetch users:', err)
      setError('获取用户列表失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setLoading(false)
    }
  }

  const filteredUsers = useMemo(() => {
    return users.filter(user => {
      if (searchText) {
        const search = searchText.toLowerCase()
        const matchUsername = user.username?.toLowerCase().includes(search)
        const matchFullName = user.full_name?.toLowerCase().includes(search)
        const matchEmail = user.email?.toLowerCase().includes(search)
        if (!matchUsername && !matchFullName && !matchEmail) {
          return false
        }
      }
      
      if (roleFilter && user.role !== roleFilter) {
        return false
      }
      
      if (statusFilter) {
        if (statusFilter === 'active' && !user.is_active) return false
        if (statusFilter === 'inactive' && user.is_active) return false
      }
      
      if (passwordStatusFilter) {
        const expired = isPasswordExpired(user)
        const expiringSoon = isPasswordExpiringSoon(user)
        
        if (passwordStatusFilter === 'expired' && !expired) return false
        if (passwordStatusFilter === 'expiring' && !expiringSoon) return false
        if (passwordStatusFilter === 'normal' && (expired || expiringSoon)) return false
      }
      
      return true
    })
  }, [users, searchText, roleFilter, statusFilter, passwordStatusFilter])

  const handleToggleActive = (user) => {
    setPendingAction({
      type: 'toggle_active',
      user,
      newValue: !user.is_active,
      message: user.is_active 
        ? `确定要禁用用户 "${user.username}" 吗？` 
        : `确定要启用用户 "${user.username}" 吗？`
    })
    setShowConfirmModal(true)
  }

  const handleChangeRole = (user, newRole) => {
    if (newRole === user.role) return
    
    setPendingAction({
      type: 'change_role',
      user,
      newValue: newRole,
      message: `确定要将用户 "${user.username}" 的角色从 "${user.role === 'admin' ? '管理员' : user.role === 'readonly'? '只读用户': 'MIS'}" 修改为 "${newRole === 'admin' ? '管理员' : newRole === 'readonly' ? '只读用户': 'MIS'}" 吗？`
    })
    setShowConfirmModal(true)
  }

  const handleDeleteUser = (user) => {
    setPendingAction({
      type: 'delete_user',
      user,
      newValue: null,
      message: `确定要删除用户 "${user.username}" 吗？此操作不可撤销。`
    })
    setShowConfirmModal(true)
  }

  const executeConfirmedAction = async () => {
    if (!pendingAction) return
    
    setActionLoading(true)
    try {
      const { type, user, newValue } = pendingAction
      
      if (type === 'toggle_active') {
        await axios.put(`${API_URL}/auth/users/${user.id}`, {
          is_active: newValue
        })
      } else if (type === 'change_role') {
        await axios.put(`${API_URL}/auth/users/${user.id}`, {
          role: newValue
        })
      } else if (type === 'delete_user') {
        await axios.delete(`${API_URL}/auth/users/${user.id}`)
      }
      
      setShowConfirmModal(false)
      setPendingAction(null)
      await fetchUsers()
    } catch (err) {
      console.error('Action failed:', err)
      alert('操作失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setActionLoading(false)
    }
  }

  const cancelConfirmAction = () => {
    setShowConfirmModal(false)
    setPendingAction(null)
    fetchUsers()
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString('zh-CN')
  }

  const getPasswordStatus = (user) => {
    if (user.role === 'admin') {
      return { status: 'admin', text: '不过期', className: 'password-admin' }
    }
    if (isPasswordExpired(user)) {
      return { status: 'expired', text: '已过期', className: 'password-expired' }
    }
    if (isPasswordExpiringSoon(user)) {
      return { status: 'expiring', text: '即将过期', className: 'password-expiring' }
    }
    return { status: 'normal', text: '正常', className: 'password-normal' }
  }

  const clearFilters = () => {
    setSearchText('')
    setRoleFilter('')
    setStatusFilter('')
    setPasswordStatusFilter('')
  }

  return (
    <div className="user-management-page">
      <div className="page-header">
        <button className="btn btn-secondary" onClick={onClose}>
          ← 返回
        </button>
        <h2>用户管理</h2>
        <button 
          className="btn btn-primary"
          onClick={() => setShowCreateModal(true)}
        >
          + 创建用户
        </button>
      </div>

      <div className="user-filters">
        <div className="filter-row">
          <div className="filter-item search-input">
            <input
              type="text"
              placeholder="搜索用户名、姓名或邮箱..."
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
            />
          </div>
          <div className="filter-item">
            <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
              <option value="">全部角色</option>
              <option value="admin">管理员</option>
              <option value="MIS">MIS</option>
              <option value="readonly">只读用户</option>
            </select>
          </div>
          <div className="filter-item">
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">全部状态</option>
              <option value="active">已启用</option>
              <option value="inactive">已禁用</option>
            </select>
          </div>
          <div className="filter-item">
            <select value={passwordStatusFilter} onChange={(e) => setPasswordStatusFilter(e.target.value)}>
              <option value="">密码状态</option>
              <option value="normal">正常</option>
              <option value="expiring">即将过期</option>
              <option value="expired">已过期</option>
            </select>
          </div>
          {(searchText || roleFilter || statusFilter || passwordStatusFilter) && (
            <button className="btn btn-sm btn-secondary" onClick={clearFilters}>
              清除筛选
            </button>
          )}
        </div>
        <div className="filter-stats">
          显示 {filteredUsers.length} / {users.length} 个用户
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {loading ? (
        <div className="loading">加载中...</div>
      ) : (
        <div className="users-table-container">
          <table className="users-table">
            <thead>
              <tr>
                <th>用户名</th>
                <th>姓名</th>
                <th>邮箱</th>
                <th>角色</th>
                <th>状态</th>
                <th>密码状态</th>
                <th>上次登录</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan="8" style={{ textAlign: 'center', padding: '40px', color: '#999' }}>
                    {users.length === 0 ? '暂无用户数据' : '没有符合条件的用户'}
                  </td>
                </tr>
              ) : (
                filteredUsers.map(user => {
                  const pwdStatus = getPasswordStatus(user)
                  // 计算当前活跃管理员总数，判断该用户是否是最后一个
                  const activeAdminCount = users.filter(u => u.role === 'admin' && u.is_active).length
                  const isLastAdmin = user.role === 'admin' && user.is_active && activeAdminCount <= 1
                  const lastAdminTip = '系统必须保留至少一个活跃的管理员账号'
                  return (
                    <tr key={user.id} className={!user.is_active ? 'inactive' : ''}>
                      <td>{user.username}</td>
                      <td>{user.full_name || '-'}</td>
                      <td>{user.email || '-'}</td>
                      <td>
                        <select
                          value={user.role}
                          onChange={(e) => handleChangeRole(user, e.target.value)}
                          className="role-select"
                          disabled={isLastAdmin}
                          title={isLastAdmin ? lastAdminTip : undefined}
                          style={isLastAdmin ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
                        >
                          <option value="MIS">MIS</option>
                          <option value="admin">管理员</option>
                          <option value="readonly">只读用户</option>
                        </select>
                      </td>
                      <td>
                        <span className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}>
                          {user.is_active ? '启用' : '禁用'}
                        </span>
                      </td>
                      <td>
                        <span className={`password-status-badge ${pwdStatus.className}`}>
                          {pwdStatus.text}
                        </span>
                      </td>
                      <td>{formatDate(user.last_login)}</td>
                      <td className="actions">
                        <button
                          className="btn btn-sm btn-secondary"
                          onClick={() => {
                            setSelectedUser(user)
                            setShowResetPasswordModal(true)
                          }}
                        >
                          重置密码
                        </button>
                        <button
                          className={`btn btn-sm ${user.is_active ? 'btn-warning' : 'btn-success'}`}
                          onClick={() => handleToggleActive(user)}
                          disabled={isLastAdmin}
                          title={isLastAdmin ? lastAdminTip : undefined}
                          style={isLastAdmin ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
                        >
                          {user.is_active ? '禁用' : '启用'}
                        </button>
                        <button
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDeleteUser(user)}
                          disabled={isLastAdmin}
                          title={isLastAdmin ? lastAdminTip : undefined}
                          style={isLastAdmin ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
                        >
                          删除
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreateModal && (
        <CreateUserModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={() => {
            setShowCreateModal(false)
            fetchUsers()
          }}
        />
      )}

      {showResetPasswordModal && selectedUser && (
        <ResetPasswordModal
          user={selectedUser}
          onClose={() => {
            setShowResetPasswordModal(false)
            setSelectedUser(null)
          }}
          onSuccess={() => {
            setShowResetPasswordModal(false)
            setSelectedUser(null)
            fetchUsers()
          }}
        />
      )}

      {showConfirmModal && pendingAction && (
        <ConfirmModal
          title="确认操作"
          message={pendingAction.message}
          warning={
            (pendingAction.type === 'delete_user')
              ? '删除用户后无法恢复，该用户的所有操作记录将保留'
              : (pendingAction.type === 'change_role' && pendingAction.user.role === 'admin')
                ? '降低管理员权限可能会影响系统管理功能'
                : (pendingAction.type === 'toggle_active' && !pendingAction.newValue && pendingAction.user.role === 'admin')
                  ? '禁用管理员账号可能会影响系统管理功能'
                  : null
          }
          loading={actionLoading}
          onConfirm={executeConfirmedAction}
          onCancel={cancelConfirmAction}
        />
      )}
    </div>
  )
}

function ConfirmModal({ title, message, warning, loading, onConfirm, onCancel }) {
  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '450px' }}>
        <div className="modal-header">
          <h2>{title}</h2>
          <button className="close-btn" onClick={onCancel}>&times;</button>
        </div>
        <div className="modal-body">
          <p style={{ fontSize: '16px', marginBottom: '15px', color: '#1F3247' }}>{message}</p>
          {warning && (
            <p style={{ color: '#E05252', fontSize: '14px', margin: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <AlertTriangle size={16} /> {warning}
            </p>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel} disabled={loading}>
            取消
          </button>
          <button className="btn btn-primary" onClick={onConfirm} disabled={loading}>
            {loading ? '处理中...' : '确认'}
          </button>
        </div>
      </div>
    </div>
  )
}

function CreateUserModal({ onClose, onSuccess }) {
  const [formData, setFormData] = useState({
    username: '',
    password: '',
    full_name: '',
    emailPrefix: '',
    emailDomain: '@zingsemi.com',
    role: 'MIS'
  })
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const emailDomains = [
    '@zingsemi.com'
  ]

  const generateRandomPassword = () => {
    const uppercase = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    const lowercase = 'abcdefghijklmnopqrstuvwxyz'
    const numbers = '0123456789'
    const symbols = '!@#$%^&*'
    
    let password = ''
    password += uppercase[Math.floor(Math.random() * uppercase.length)]
    password += lowercase[Math.floor(Math.random() * lowercase.length)]
    password += numbers[Math.floor(Math.random() * numbers.length)]
    password += symbols[Math.floor(Math.random() * symbols.length)]
    
    const allChars = uppercase + lowercase + numbers + symbols
    for (let i = 0; i < 4; i++) {
      password += allChars[Math.floor(Math.random() * allChars.length)]
    }
    
    password = password.split('').sort(() => Math.random() - 0.5).join('')
    
    setFormData({...formData, password})
    setShowPassword(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    const submitData = {
      username: formData.username,
      password: formData.password,
      full_name: formData.full_name,
      email: formData.emailPrefix ? formData.emailPrefix + formData.emailDomain : '',
      role: formData.role
    }

    try {
      await axios.post(`${API_URL}/auth/users`, submitData)
      onSuccess()
    } catch (err) {
      setError(err.response?.data?.detail || '创建用户失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '500px' }}>
        <div className="modal-header">
          <h2>创建用户</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="form-error">{error}</div>}
            
            <div className="form-group">
              <label>用户名 *</label>
              <input
                type="text"
                value={formData.username}
                onChange={(e) => setFormData({...formData, username: e.target.value})}
                placeholder="请输入用户名"
                required
              />
            </div>
            
            <div className="form-group">
              <label>密码 *</label>
              <div className="password-input-group">
                <input
                  type={showPassword ? "text" : "password"}
                  value={formData.password}
                  onChange={(e) => setFormData({...formData, password: e.target.value})}
                  placeholder="请输入密码（至少）"
                  required
                />
                <button 
                  type="button" 
                  className="btn btn-sm btn-secondary"
                  onClick={() => setShowPassword(!showPassword)}
                  title={showPassword ? "隐藏密码" : "显示密码"}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
                <button 
                  type="button" 
                  className="btn btn-sm btn-primary"
                  onClick={generateRandomPassword}
                  title="生成随机密码"
                >
                  生成
                </button>
              </div>
            </div>
            
            <div className="form-row">
              <div className="form-group">
                <label>姓名</label>
                <input
                  type="text"
                  value={formData.full_name}
                  onChange={(e) => setFormData({...formData, full_name: e.target.value})}
                  placeholder="请输入姓名"
                />
              </div>
              
              <div className="form-group">
                <label>角色</label>
                <select
                  value={formData.role}
                  onChange={(e) => setFormData({...formData, role: e.target.value})}
                >
                  <option value="MIS">MIS</option>
                  <option value="admin">管理员</option>
                  <option value="readonly">只读用户</option>
                </select>
              </div>
            </div>
            
            <div className="form-group">
              <label>邮箱</label>
              <div className="email-input-group">
                <input
                  type="text"
                  value={formData.emailPrefix}
                  onChange={(e) => setFormData({...formData, emailPrefix: e.target.value})}
                  placeholder="邮箱前缀"
                />
                <select
                  value={formData.emailDomain}
                  onChange={(e) => setFormData({...formData, emailDomain: e.target.value})}
                >
                  {emailDomains.map(domain => (
                    <option key={domain} value={domain}>{domain}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? '创建中...' : '创建用户'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function ResetPasswordModal({ user, onClose, onSuccess }) {
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (newPassword !== confirmPassword) {
      setError('两次输入的密码不一致')
      return
    }

    if (newPassword.length < 8) {
      setError('密码长度至少8位')
      return
    }

    setLoading(true)
    try {
      await axios.put(`${API_URL}/auth/users/${user.id}/reset-password`, {
        new_password: newPassword
      })
      alert('用户 ' + user.username + ' 的密码已重置')
      onSuccess()
    } catch (err) {
      setError(err.response?.data?.detail || '重置密码失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '450px' }}>
        <div className="modal-header">
          <h2>重置密码 - {user.username}</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && <div className="form-error">{error}</div>}
            
            <div className="form-group">
              <label>新密码</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="请输入新密码（至少8位）"
                required
              />
            </div>
            
            <div className="form-group">
              <label>确认密码</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="请再次输入新密码"
                required
              />
            </div>
          </div>
          
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>
              取消
            </button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? '重置中...' : '确认重置'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default UserManagement
