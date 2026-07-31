import { useState, useEffect } from 'react'
import axios from 'axios'
import { Package, History } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''

function ReturnManagement({ onAssetClick }) {
  const {isReadyOnly: isReadOnly} = useAuth()
  const navigate = useNavigate()
  const [returnRecords, setReturnRecords] = useState([])
  const [idleAssetsCount, setIdleAssetsCount] = useState(0)
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingRecord, setEditingRecord] = useState(null)
  const [activeTab, setActiveTab] = useState('pending')


  useEffect(() => {
    fetchReturnRecords()
    fetchIdleAssetsCount()
    fetchStats()
  }, [])

  const fetchReturnRecords = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_URL}/return-records/`)
      setReturnRecords(response.data)
    } catch (error) {
      console.error('获取归还记录失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchIdleAssetsCount = async () => {
    try {
      // 获取所有闲置状态的资产数量（与资产管理页面一致）
      const response = await axios.get(`${API_URL}/assets/`, { params: { status: '闲置' } })
      setIdleAssetsCount(response.data.length)
    } catch (error) {
      console.error('获取闲置资产数量失败:', error)
    }
  }

  const fetchStats = async () => {
    try {
      const response = await axios.get(`${API_URL}/return-records/stats`)
      setStats(response.data)
    } catch (error) {
      console.error('获取统计数据失败:', error)
    }
  }

  const handleAddRecord = () => {
    setEditingRecord(null)
    setShowModal(true)
  }

  const handleEditRecord = (record) => {
    setEditingRecord(record)
    setShowModal(true)
  }

  const handleSaveRecord = async (recordData) => {
    try {
      if (editingRecord) {
        await axios.put(`${API_URL}/return-records/${editingRecord.id}`, recordData)
      } else {
        await axios.post(`${API_URL}/return-records/`, recordData)
      }
      setShowModal(false)
      fetchReturnRecords()
      fetchStats()
    } catch (error) {
      console.error('保存归还记录失败:', error)
      alert('保存归还记录失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const formatDate = (dateString) => {
    return dateString ? new Date(dateString).toLocaleString('zh-CN') : '-'
  }

  const pendingRecords = returnRecords.filter(r => !r.is_returned)
  const completedRecords = returnRecords.filter(r => r.is_returned)

  return (
    <div className="return-management">
      <div className="return-header">
        <h2>资产归还管理</h2>
        <div className="header-actions">
          <button className="btn btn-secondary" onClick={() => navigate('/returns/history')}>
            <History size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} /> 归还历史
          </button>
          <button className="btn btn-secondary" onClick={() => {
            window.dispatchEvent(new CustomEvent('switchToIdleAssets'))
          }}>
            <Package size={16} style={{ verticalAlign: 'middle', marginRight: 4 }} /> 库房闲置
          </button>
          {!isReadOnly && (
          <button className="btn btn-primary" onClick={handleAddRecord}>
            + 添加归还记录
           </button>
          )}
        </div>
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card" style={{ borderLeft: '4px solid #D4952B' }}>
            <div className="stat-value">{stats.pending_count}</div>
            <div className="stat-label">待归还</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '4px solid #3A9E75' }}>
            <div className="stat-value">{stats.returned_count}</div>
            <div className="stat-label">已归还</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '4px solid #375B81' }}>
            <div className="stat-value">{idleAssetsCount}</div>
            <div className="stat-label">库房闲置</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '4px solid #7792CF' }}>
            <div className="stat-value">{stats.total_records}</div>
            <div className="stat-label">总记录数</div>
          </div>
        </div>
      )}

      {/* 标签页 */}
      <div className="nav-tabs">
        <button 
          className={`nav-tab ${activeTab === 'pending' ? 'active' : ''}`}
          onClick={() => setActiveTab('pending')}
        >
          待归还 ({pendingRecords.length})
        </button>
        <button 
          className={`nav-tab ${activeTab === 'completed' ? 'active' : ''}`}
          onClick={() => setActiveTab('completed')}
        >
          已归还 ({completedRecords.length})
        </button>
      </div>

      {loading ? (
        <div className="loading">加载中...</div>
      ) : (
        <div className="return-content">
          {activeTab === 'pending' && (
            <ReturnRecordList 
              records={pendingRecords} 
              onEdit={handleEditRecord}
              title="待归还记录"
              emptyMessage="暂无待归还记录"
              isReadyOnly={isReadOnly}
            />
          )}
          
          {activeTab === 'completed' && (
            <ReturnRecordList 
              records={completedRecords} 
              onEdit={handleEditRecord}
              title="已归还记录"
              emptyMessage="暂无已归还记录"
              isReadyOnly={isReadOnly}
            />
          )}
        </div>
      )}

      {/* 模态框 */}
      {showModal && (
        <ReturnRecordModal
          record={editingRecord}
          onClose={() => setShowModal(false)}
          onSave={handleSaveRecord}
        />
      )}
    </div>
  )
}

function ReturnRecordList({ records, onEdit, title, emptyMessage, isReadyOnly }) {
  const formatDate = (dateString) => {
    return dateString ? new Date(dateString).toLocaleString('zh-CN') : '-'
  }

  if (records.length === 0) {
    return (
      <div className="empty-state">
        <h3>{emptyMessage}</h3>
      </div>
    )
  }

  return (
    <div className="return-records">
      <div className="records-grid">
        {records.map(record => (
          <div key={record.id} className="record-card">
            <div className="record-header">
              <div className="employee-info">
                <div className="employee-name">{record.employee_name}</div>
                <div className="employee-id">工号: {record.employee_id}</div>
              </div>
              <div className={`return-status ${record.is_returned ? 'returned' : 'pending'}`}>
                {record.is_returned ? '已归还' : '待归还'}
              </div>
            </div>
            
            <div className="record-details">
              <div className="record-detail"><strong>部门:</strong> {record.department || '-'}</div>
              <div className="record-detail"><strong>归还原因:</strong> {record.return_reason}</div>
              <div className="record-detail"><strong>创建时间:</strong> {formatDate(record.created_at)}</div>
              {record.return_date && (
                <div className="record-detail"><strong>归还时间:</strong> {formatDate(record.return_date)}</div>
              )}
              {record.notes && (
                <div className="record-detail"><strong>备注:</strong> {record.notes}</div>
              )}
            </div>

            {!isReadyOnly && (
            <div className="record-actions">
              <button className="btn btn-edit" onClick={() => onEdit(record)}>
                {record.is_returned ? '查看详情' : '处理归还'}
              </button>
            </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function ReturnedAssetsList({ assets, onAssetClick }) {
  if (assets.length === 0) {
    return (
      <div className="empty-state">
        <h3>暂无库房闲置资产</h3>
      </div>
    )
  }

  return (
    <div className="returned-assets">
      <div className="assets-grid">
        {assets.map(asset => (
          <div 
            key={asset.id} 
            className="asset-card clickable"
            onClick={() => onAssetClick && onAssetClick(asset)}
            style={{ cursor: 'pointer' }}
          >
            <div className="asset-header">
              <div className="asset-tag">{asset.asset_tag}</div>
              <span className="status-badge status-闲置">闲置</span>
            </div>
            
            <div className="asset-details">
              <div className="asset-detail"><strong>品类:</strong> {asset.category}</div>
              <div className="asset-detail"><strong>品牌:</strong> {asset.brand || '-'}</div>
              <div className="asset-detail"><strong>型号:</strong> {asset.model || '-'}</div>
              <div className="asset-detail"><strong>固定资产编号:</strong> {asset.fixed_asset_number || '-'}</div>
              {asset.hostname && (
                <div className="asset-detail"><strong>资产名:</strong> {asset.hostname}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function ReturnRecordModal({ record, onClose, onSave }) {
  const [formData, setFormData] = useState({
    asset_name: '',
    employee_id: '',
    employee_name: '',
    department: '',
    return_reason: '',
    is_returned: false,
    return_date: '',
    notes: ''
  })
  const [departments, setDepartments] = useState([])
  const [activeAssets, setActiveAssets] = useState([])

  useEffect(() => {
    axios.get(`${API_URL}/departments/flat`).then(res => setDepartments(res.data)).catch(() => {})
    // 加载使用中的资产，用于资产名下拉选择
    axios.get(`${API_URL}/assets/`, { params: { status: '使用中', limit: 10000 } })
      .then(res => setActiveAssets(res.data))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (record) {
      setFormData({
        asset_name: record.asset_name || '',
        employee_id: record.employee_id || '',
        employee_name: record.employee_name || '',
        department: record.department || '',
        return_reason: record.return_reason || '',
        is_returned: record.is_returned || false,
        return_date: record.return_date ? record.return_date.split('T')[0] : '',
        notes: record.notes || ''
      })
    }
  }, [record])

  const handleAssetSelect = (e) => {
    const selectedHostname = e.target.value
    const asset = activeAssets.find(a => (a.hostname || a.asset_tag) === selectedHostname)
    if (asset) {
      setFormData(prev => ({
        ...prev,
        asset_name: selectedHostname,
        employee_name: asset.employee_name || prev.employee_name,
        employee_id: asset.employee_id || prev.employee_id,
        department: asset.department || prev.department,
      }))
    } else {
      setFormData(prev => ({ ...prev, asset_name: selectedHostname }))
    }
  }

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target
    setFormData({
      ...formData,
      [name]: type === 'checkbox' ? checked : value
    })
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const dataToSend = { ...formData }
    // 空字符串的 return_date 转为 null，避免后端 Pydantic 验证失败
    if (dataToSend.return_date) {
      dataToSend.return_date = new Date(dataToSend.return_date).toISOString()
    } else {
      dataToSend.return_date = null
    }
    // 可选字符串字段：空字符串转 null
    if (!dataToSend.department) dataToSend.department = null
    if (!dataToSend.notes) dataToSend.notes = null
    onSave(dataToSend)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{record ? '编辑归还记录' : '添加归还记录'}</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="form-row">
              <div className="form-group">
                <label>资产名 *</label>
                {record ? (
                  // 编辑模式：只读显示
                  <input
                    type="text"
                    value={formData.asset_name}
                    disabled
                    style={{ opacity: 0.7, cursor: 'not-allowed' }}
                  />
                ) : (
                  // 新建模式：从使用中资产选择
                  <select
                    name="asset_name"
                    value={formData.asset_name}
                    onChange={handleAssetSelect}
                    required
                  >
                    <option value="">选择资产</option>
                    {activeAssets.map(a => (
                      <option key={a.id} value={a.hostname || a.asset_tag}>
                        {a.hostname || a.asset_tag}
                        {a.employee_name ? ` — ${a.employee_name}` : ''}
                        {a.category ? ` (${a.category})` : ''}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div className="form-group">
                <label>员工工号 *</label>
                <input
                  type="text"
                  name="employee_id"
                  value={formData.employee_id}
                  onChange={handleChange}
                  required
                />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>员工姓名 *</label>
                <input
                  type="text"
                  name="employee_name"
                  value={formData.employee_name}
                  onChange={handleChange}
                  required
                />
              </div>
              <div className="form-group">
                <label>部门</label>
                <select
                  name="department"
                  value={formData.department}
                  onChange={handleChange}
                >
                  <option value="">选择部门</option>
                  {departments.map(d => <option key={d.id} value={d.display}>{d.display}</option>)}
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>归还原因 *</label>
                <select name="return_reason" value={formData.return_reason} onChange={handleChange} required>
                  <option value="">选择归还原因</option>
                  <option value="离职">离职</option>
                  <option value="调岗">调岗</option>
                  <option value="设备更换">设备更换</option>
                  <option value="其他">其他</option>
                </select>
              </div>
              <div className="form-group">
                <label>归还状态</label>
                <select name="is_returned" value={formData.is_returned ? 'true' : 'false'} onChange={(e) => {
                  setFormData({
                    ...formData,
                    is_returned: e.target.value === 'true'
                  })
                }}>
                  <option value="false">待归还</option>
                  <option value="true">已归还</option>
                </select>
              </div>
            </div>
            {formData.is_returned && (
              <div className="form-group">
                <label>归还时间</label>
                <input
                  type="date"
                  name="return_date"
                  value={formData.return_date}
                  onChange={handleChange}
                />
              </div>
            )}
            <div className="form-group">
              <label>备注</label>
              <textarea
                name="notes"
                value={formData.notes}
                onChange={handleChange}
                rows="3"
              />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>取消</button>
            <button type="submit" className="btn btn-primary">保存</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default ReturnManagement