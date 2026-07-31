import { useState, useEffect } from 'react'
import axios from 'axios'
import {useAuth} from '../contexts/AuthContext'
import { Package } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// 资产状况配置：标签、颜色
const CONDITION_CONFIG = {
  '可用':   { label: '可用',   bg: '#d1fae5', color: '#065f46', border: '#6ee7b7' },
  '损坏':   { label: '损坏',   bg: '#ffedd5', color: '#9a3412', border: '#fdba74' },
  '待报废': { label: '待报废', bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
}

function ConditionBadge({ condition }) {
  const cfg = CONDITION_CONFIG[condition] || CONDITION_CONFIG['可用']
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      fontSize: 12,
      fontWeight: 600,
      background: cfg.bg,
      color: cfg.color,
      border: `1px solid ${cfg.border}`,
      whiteSpace: 'nowrap',
    }}>
      {cfg.label}
    </span>
  )
}

function IdleAssets({ onAssetSelect, selectedAsset }) {
  const {isReadOnly} = useAuth()
  const [idleAssets, setIdleAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [assigningAsset, setAssigningAsset] = useState(null)
  const [assignData, setAssignData] = useState({ employee_name: '', employee_id: '', department: '' })
  const [filters, setFilters] = useState({ search: '', category: '', location: '' })
  const [departments, setDepartments] = useState([])
  const [showBatchAssignModal, setShowBatchAssignModal] = useState(false)
  const [batchAssignData, setBatchAssignData] = useState({ employee_name: '', employee_id: '', department: '' })
  // 正在修改状况的资产 id（用于显示下拉）
  const [editingConditionId, setEditingConditionId] = useState(null)

  useEffect(() => { fetchIdleAssets() }, [filters])
  useEffect(() => { axios.get(`${API_URL}/departments/flat`).then(res => setDepartments(res.data)).catch(() => {}) }, [])

  const fetchIdleAssets = async () => {
    try {
      setLoading(true)
      const params = { status: '闲置', ...Object.fromEntries(Object.entries(filters).filter(([_, v]) => v)) }
      const response = await axios.get(`${API_URL}/assets/`, { params })
      setIdleAssets(response.data)
    } catch (error) { console.error('获取闲置资产失败:', error) }
    finally { setLoading(false) }
  }

  const handleFilterChange = (e) => { setFilters({ ...filters, [e.target.name]: e.target.value }) }

  // 修改单个资产的状况
  const handleConditionChange = async (asset, newCondition) => {
    setEditingConditionId(null)
    if (newCondition === asset.condition) return
    try {
      await axios.put(`${API_URL}/assets/${asset.id}`, { condition: newCondition })
      setIdleAssets(prev => prev.map(a => a.id === asset.id ? { ...a, condition: newCondition } : a))
    } catch (error) {
      alert('更新状况失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const handleAssignSubmit = async (e) => {
    e.preventDefault()
    if (!assignData.employee_name.trim()) { alert('请输入员工姓名'); return }
    if (!assignData.employee_id.trim()) { alert('请输入工号'); return }
    try {
      await axios.put(`${API_URL}/assets/${assigningAsset.id}`, {
        employee_name: assignData.employee_name.trim(),
        employee_id: assignData.employee_id.trim(),
        department: assignData.department.trim(),
        status: '使用中',
        issue_date: new Date().toISOString()
      })
      setShowAssignModal(false)
      setAssignData({ employee_name: '', employee_id: '', department: '' })
      fetchIdleAssets()
      if (selectedAsset && selectedAsset.id === assigningAsset.id) onAssetSelect(null)
    } catch (error) { alert('分配失败: ' + (error.response?.data?.detail || error.message)) }
  }

  const handleBatchAssign = () => {
    if (idleAssets.filter(a => a.selected).length === 0) { alert('请先选择要分配的资产'); return }
    setShowBatchAssignModal(true)
  }

  const handleBatchAssignSubmit = async (e) => {
    e.preventDefault()
    if (!batchAssignData.employee_name.trim()) { alert('请输入员工姓名'); return }
    if (!batchAssignData.employee_id.trim()) { alert('请输入工号'); return }
    const selected = idleAssets.filter(a => a.selected)
    try {
      await Promise.all(selected.map(asset =>
        axios.put(`${API_URL}/assets/${asset.id}`, {
          employee_name: batchAssignData.employee_name.trim(),
          employee_id: batchAssignData.employee_id.trim(),
          department: batchAssignData.department.trim(),
          status: '使用中',
          issue_date: new Date().toISOString()
        })
      ))
      setShowBatchAssignModal(false)
      setBatchAssignData({ employee_name: '', employee_id: '', department: '' })
      fetchIdleAssets()
      alert(`成功分配 ${selected.length} 个资产`)
    } catch (error) { alert('批量分配失败: ' + (error.response?.data?.detail || error.message)) }
  }

  const toggleAssetSelection = (assetId) => {
    setIdleAssets(prev => prev.map(a => a.id === assetId ? { ...a, selected: !a.selected } : a))
  }

  if (loading) return <div className="loading">加载闲置资产中...</div>

  return (
    <div className="idle-assets-container">
      <div className="idle-assets-header">
        <div className="header-info">
          <h2>库房闲置资产</h2>
          <p className="subtitle">共 {idleAssets.length} 个闲置资产可供分配</p>
        </div>
        <div className="header-actions">
          {!isReadOnly && (
          <button className="btn btn-primary" onClick={handleBatchAssign}>批量分配</button>
          )}
        </div>
      </div>

      <div className="idle-filters">
        <input type="text" name="search" placeholder="搜索资产标签、资产名、型号..." value={filters.search} onChange={handleFilterChange} className="filter-input" />
        <select name="category" value={filters.category} onChange={handleFilterChange} className="filter-select">
          <option value="">所有品类</option>
          <option value="台式机">台式机</option>
          <option value="笔记本电脑">笔记本电脑</option>
          <option value="移动设备">移动设备</option>
          <option value="手机">手机</option>
          <option value="无线鼠标">无线鼠标</option>
          <option value="显示器">显示器</option>
          <option value="打印机">打印机</option>
          <option value="网络设备">网络设备</option>
          <option value="其他设备">其他设备</option>
        </select>
      </div>

      {idleAssets.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><Package size={48} /></div>
          <h3>暂无闲置资产</h3>
          <p>所有资产都已分配或处于其他状态</p>
        </div>
      ) : (
        <div className="idle-content">
          <div className="idle-assets-list">
            {idleAssets.map(asset => (
              <div
                key={asset.id}
                className={`idle-asset-row ${selectedAsset?.id === asset.id ? 'selected' : ''}`}
                // 点击行外区域时关闭状况下拉
                onClick={() => editingConditionId === asset.id && setEditingConditionId(null)}
              >
                <div className="asset-row-main" onClick={() => onAssetSelect(asset)}>
                  <div className="asset-row-checkbox">
                    <input type="checkbox" checked={asset.selected || false}
                      onChange={(e) => { e.stopPropagation(); toggleAssetSelection(asset.id) }}
                      onClick={(e) => e.stopPropagation()} />
                  </div>
                  <div className="asset-row-info">
                    <div className="asset-row-title">
                      <span className="asset-name">{asset.hostname || asset.asset_tag}</span>
                      <span className="asset-category">{asset.category}</span>
                      <span className="status-badge status-闲置">闲置</span>
                      {/* 资产状况徽章，点击展开修改下拉 */}
                      <span
                        style={{ position: 'relative', display: 'inline-block' }}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (!isReadOnly) {
                          setEditingConditionId(editingConditionId === asset.id ? null : asset.id)
                          }
                        }}
                        title="点击修改资产状况"
                      >
                        <ConditionBadge condition={asset.condition || '可用'} />
                        {editingConditionId === asset.id && (
                          <div
                            style={{
                              position: 'absolute',
                              top: '110%',
                              left: 0,
                              zIndex: 100,
                              background: '#fff',
                              border: '1px solid var(--color-border)',
                              borderRadius: 6,
                              boxShadow: '0 4px 12px rgba(0,0,0,0.12)',
                              minWidth: 100,
                              overflow: 'hidden',
                            }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {Object.keys(CONDITION_CONFIG).map(cond => (
                              <div
                                key={cond}
                                style={{
                                  padding: '8px 14px',
                                  cursor: 'pointer',
                                  fontSize: 13,
                                  background: (asset.condition || '可用') === cond ? 'var(--color-bg)' : '#fff',
                                  fontWeight: (asset.condition || '可用') === cond ? 600 : 400,
                                }}
                                onMouseEnter={e => e.currentTarget.style.background = 'var(--color-bg)'}
                                onMouseLeave={e => e.currentTarget.style.background = (asset.condition || '可用') === cond ? 'var(--color-bg)' : '#fff'}
                                onClick={() => handleConditionChange(asset, cond)}
                              >
                                <ConditionBadge condition={cond} />
                              </div>
                            ))}
                          </div>
                        )}
                      </span>
                    </div>
                    <div className="asset-row-details">
                      {asset.brand && <span className="asset-detail-item">品牌: {asset.brand}</span>}
                      {asset.model && <span className="asset-detail-item">型号: {asset.model}</span>}
                      {asset.serial_number && <span className="asset-detail-item">序列号: {asset.serial_number}</span>}
                    </div>
                  </div>
                </div>
                <div className="asset-row-actions">
                  {isReadOnly && (
                  <button className="btn btn-sm btn-primary" onClick={(e) => { e.stopPropagation(); setAssigningAsset(asset); setShowAssignModal(true) }}>分配</button>
                  )}
                  <button className="btn btn-sm btn-secondary" onClick={(e) => { e.stopPropagation(); onAssetSelect(asset) }}>详情</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {showAssignModal && assigningAsset && (
        <div className="modal-overlay" onClick={() => setShowAssignModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>分配资产: {assigningAsset.hostname || assigningAsset.asset_tag}</h2>
              <button className="close-btn" onClick={() => setShowAssignModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleAssignSubmit}>
              <div className="modal-body">
                <div className="form-group"><label>员工姓名 *</label>
                  <input type="text" value={assignData.employee_name} onChange={(e) => setAssignData({...assignData, employee_name: e.target.value})} placeholder="请输入员工姓名" required />
                </div>
                <div className="form-group"><label>工号 *</label>
                  <input type="text" value={assignData.employee_id} onChange={(e) => setAssignData({...assignData, employee_id: e.target.value})} placeholder="请输入工号" required />
                </div>
                <div className="form-group"><label>部门</label>
                  <select value={assignData.department} onChange={(e) => setAssignData({...assignData, department: e.target.value})}>
                    <option value="">选择部门</option>
                    {departments.map(d => <option key={d.id} value={d.display}>{d.display}</option>)}
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAssignModal(false)}>取消</button>
                <button type="submit" className="btn btn-primary">确认分配</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showBatchAssignModal && (
        <div className="modal-overlay" onClick={() => setShowBatchAssignModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>批量分配资产 ({idleAssets.filter(a => a.selected).length} 个)</h2>
              <button className="close-btn" onClick={() => setShowBatchAssignModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleBatchAssignSubmit}>
              <div className="modal-body">
                <div className="form-group"><label>员工姓名 *</label>
                  <input type="text" value={batchAssignData.employee_name} onChange={(e) => setBatchAssignData({...batchAssignData, employee_name: e.target.value})} placeholder="请输入员工姓名" required />
                </div>
                <div className="form-group"><label>工号 *</label>
                  <input type="text" value={batchAssignData.employee_id} onChange={(e) => setBatchAssignData({...batchAssignData, employee_id: e.target.value})} placeholder="请输入工号" required />
                </div>
                <div className="form-group"><label>部门</label>
                  <select value={batchAssignData.department} onChange={(e) => setBatchAssignData({...batchAssignData, department: e.target.value})}>
                    <option value="">选择部门</option>
                    {departments.map(d => <option key={d.id} value={d.display}>{d.display}</option>)}
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowBatchAssignModal(false)}>取消</button>
                <button type="submit" className="btn btn-primary">确认分配</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default IdleAssets
