import { useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

function ChangePassword({ required = false, onSuccess, onCancel }) {
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { changePassword } = useAuth()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    if (newPassword !== confirmPassword) {
      setError('两次输入的新密码不一致')
      return
    }

    if (newPassword.length < 6) {
      setError('新密码长度至少6位')
      return
    }

    setLoading(true)
    try {
      await changePassword(oldPassword, newPassword)
      onSuccess?.()
    } catch (err) {
      setError(err.response?.data?.detail || '密码修改失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '450px' }}>
        <div className="modal-header">
          <h2>{required ? '密码已过期，请修改密码' : '修改密码'}</h2>
          {!required && (
            <button className="close-btn" onClick={onCancel}>&times;</button>
          )}
        </div>
        
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {required && (
              <div className="password-expired-notice">
                您的密码已超过90天未修改，为了账号安全，请立即修改密码。
              </div>
            )}
            
            {error && <div className="form-error">{error}</div>}
            
            <div className="form-group">
              <label htmlFor="oldPassword">当前密码</label>
              <input
                type="password"
                id="oldPassword"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                placeholder="请输入当前密码"
                required
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="newPassword">新密码</label>
              <input
                type="password"
                id="newPassword"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="请输入新密码（至少）"
                required
              />
            </div>
            
            <div className="form-group">
              <label htmlFor="confirmPassword">确认新密码</label>
              <input
                type="password"
                id="confirmPassword"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="请再次输入新密码"
                required
              />
            </div>
          </div>
          
          <div className="modal-footer">
            {!required && (
              <button type="button" className="btn btn-secondary" onClick={onCancel}>
                取消
              </button>
            )}
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? '提交中...' : '确认修改'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ChangePassword
