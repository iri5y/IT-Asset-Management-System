import { useState, useEffect } from 'react'
import axios from 'axios'
import {useAuth} from '../contexts/AuthContext'
import { X, AlertTriangle, CheckCircle } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

function WarehouseAssetDetail({ asset, onClose, onEdit, onDelete, onRefresh, onBackToHome, isAdmin }) {
  const {isReadOnly} = useAuth()
  const [loading, setLoading] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [successMessage, setSuccessMessage] = useState('')
  const [warehouseLogs, setWarehouseLogs] = useState([])
  const [logsLoading, setLogsLoading] = useState(false)
  const [departments, setDepartments] = useState([])
  const [currentAsset, setCurrentAsset] = useState(asset)
  const [assignData, setAssignData] = useState({
    employee_name: '',
    employee_id: '',
    department: '',
    assign_quantity: 1,
    asset_display_name: asset?.name || '',
    notes: '',
  })

  // 当传入的asset发生变化时，更新本地状态
  useEffect(() => {
    setCurrentAsset(asset)
    if (asset) fetchWarehouseLogs(asset.id)
  }, [asset])

  useEffect(() => {
    axios.get(`${API_URL}/departments/flat`).then(res => setDepartments(res.data)).catch(() => {})
  }, [])

  const fetchWarehouseLogs = async (id) => {
    try {
      setLogsLoading(true)
      const response = await axios.get(`${API_URL}/warehouse/${id}/logs`)
      setWarehouseLogs(response.data)
    } catch (error) {
      console.error('获取库房操作日志失败:', error)
    } finally {
      setLogsLoading(false)
    }
  }

  if (!currentAsset) return null

  const handleEdit = () => {
    onEdit(currentAsset)
  }

  const handleDelete = async () => {
    try {
      setLoading(true)
      await axios.delete(`${API_URL}/warehouse/${currentAsset.id}`)
      onDelete(currentAsset.id)
      onClose()
      if (onRefresh) onRefresh()
    } catch (error) {
      console.error('删除库房资产失败:', error)
      alert('删除库房资产失败')
    } finally {
      setLoading(false)
      setShowDeleteModal(false)
    }
  }

  const handleAssign = () => {
    setAssignData({
      employee_name: '',
      employee_id: '',
      department: '',
      assign_quantity: 1,
      asset_display_name: currentAsset.name,
      notes: '',
    })
    setShowAssignModal(true)
  }

  const handleAssignSubmit = async (e) => {
    e.preventDefault()

    try {
      setLoading(true)
      const qty = parseInt(assignData.assign_quantity) || 1
      const freshResponse = await axios.get(`${API_URL}/warehouse/${currentAsset.id}`)
      const freshAsset = freshResponse.data

      if (qty > freshAsset.available_quantity) {
        alert(`可用库存不足，当前实际可用: ${freshAsset.available_quantity}`)
        setCurrentAsset(freshAsset)
        return
      }

      const dispatchParts = [`领用 ${qty} 个「${currentAsset.name}」`]
      if (assignData.employee_name) dispatchParts.push(`领用人: ${assignData.employee_name}`)
      if (assignData.employee_id) dispatchParts.push(`工号: ${assignData.employee_id}`)
      if (assignData.department) dispatchParts.push(`部门: ${assignData.department}`)
      if (assignData.notes) dispatchParts.push(`备注: ${assignData.notes}`)

      await axios.put(`${API_URL}/warehouse/${currentAsset.id}`, {
        available_quantity: freshAsset.available_quantity - qty,
        allocated_quantity: freshAsset.allocated_quantity + qty,
        dispatch_note: dispatchParts.join('，'),
      })

      try {
        const updatedResponse = await axios.get(`${API_URL}/warehouse/${currentAsset.id}`)
        setCurrentAsset(updatedResponse.data)
      } catch {
        setCurrentAsset({
          ...currentAsset,
          available_quantity: freshAsset.available_quantity - qty,
          allocated_quantity: freshAsset.allocated_quantity + qty,
        })
      }

      if (onRefresh) onRefresh()
      setShowAssignModal(false)
      const recipientInfo = assignData.employee_name ? ` 给 ${assignData.employee_name}` : ''
      setSuccessMessage(`已成功领用 ${qty} 个 ${currentAsset.name}${recipientInfo}`)
      setShowSuccessModal(true)
    } catch (error) {
      console.error('领用出库失败:', error)
      alert('领用出库失败: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const getStockStatus = () => {
    if (currentAsset.available_quantity <= currentAsset.minimum_stock) {
      return { status: 'low', color: '#E05252', text: '库存不足' }
    } else if (currentAsset.available_quantity <= currentAsset.minimum_stock * 2) {
      return { status: 'medium', color: '#D4952B', text: '库存偏低' }
    } else {
      return { status: 'good', color: '#3A9E75', text: '库存充足' }
    }
  }

  const stockStatus = getStockStatus()
  const utilizationRate = currentAsset.total_quantity > 0 ? ((currentAsset.allocated_quantity / currentAsset.total_quantity) * 100).toFixed(1) : 0

  return (
    <div className="warehouse-asset-detail-fullpage">
      <div className="warehouse-detail-header">
        <div className="warehouse-detail-title">
          <h2>{currentAsset.name}</h2>
          <div 
            className="stock-status-badge"
            style={{ backgroundColor: stockStatus.color }}
          >
            {stockStatus.text}
          </div>
        </div>
        <div className="warehouse-detail-actions-top">
          <button className="btn btn-secondary" onClick={onBackToHome || onClose}>
            ← 返回主页
          </button>
          <button className="close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="warehouse-detail-content">
        {/* 基本信息 */}
        <div className="detail-info-block">
          <div className="detail-section-label">基本信息</div>
          <div className="detail-grid compact">
            <div className="detail-item">
              <div className="detail-label">资产名称</div>
              <div className="detail-value">{currentAsset.name}</div>
            </div>
            <div className="detail-item">
              <div className="detail-label">品类</div>
              <div className="detail-value">{currentAsset.category}</div>
            </div>
            {currentAsset.subcategory && (
              <div className="detail-item">
                <div className="detail-label">子分类</div>
                <div className="detail-value">{currentAsset.subcategory}</div>
              </div>
            )}
            {currentAsset.brand && (
              <div className="detail-item">
                <div className="detail-label">品牌</div>
                <div className="detail-value">{currentAsset.brand}</div>
              </div>
            )}
            {currentAsset.model && (
              <div className="detail-item">
                <div className="detail-label">型号</div>
                <div className="detail-value">{currentAsset.model}</div>
              </div>
            )}
            {currentAsset.specifications && (
              <div className="detail-item">
                <div className="detail-label">规格</div>
                <div className="detail-value">{currentAsset.specifications}</div>
              </div>
            )}
            <div className="detail-item">
              <div className="detail-label">存放位置</div>
              <div className="detail-value">{currentAsset.location || '-'}</div>
            </div>
          </div>
        </div>

        {/* 库存信息 */}
        <div className="detail-info-block">
          <div className="detail-section-label">库存信息</div>
          <div className="stock-overview">
            <div className="stock-card">
              <div className="stock-number font-data">{currentAsset.total_quantity}</div>
              <div className="stock-label">总数量</div>
            </div>
            <div className="stock-card" style={{ borderColor: stockStatus.color }}>
              <div className="stock-number font-data" style={{ color: stockStatus.color }}>
                {currentAsset.available_quantity}
              </div>
              <div className="stock-label">可用数量</div>
            </div>
            <div className="stock-card">
              <div className="stock-number font-data">{currentAsset.allocated_quantity}</div>
              <div className="stock-label">已分配</div>
            </div>
            <div className="stock-card">
              <div className="stock-number font-data">{currentAsset.minimum_stock}</div>
              <div className="stock-label">最低库存</div>
            </div>
          </div>

          {/* 库存状态条 */}
          <div className="stock-bar-container">
            <div className="stock-bar-label">库存分布</div>
            <div className="stock-bar">
              <div 
                className="stock-bar-allocated"
                style={{ 
                  width: `${(currentAsset.allocated_quantity / currentAsset.total_quantity) * 100}%`,
                  backgroundColor: '#375B81'
                }}
              />
              <div 
                className="stock-bar-available"
                style={{ 
                  width: `${(currentAsset.available_quantity / currentAsset.total_quantity) * 100}%`,
                  backgroundColor: stockStatus.color
                }}
              />
            </div>
            <div className="stock-bar-legend">
              <span><span className="legend-color" style={{ backgroundColor: '#375B81' }}></span> 已分配 ({currentAsset.allocated_quantity})</span>
              <span><span className="legend-color" style={{ backgroundColor: stockStatus.color }}></span> 可用 ({currentAsset.available_quantity})</span>
            </div>
          </div>

          {/* 利用率 */}
          <div className="utilization-info">
            <div className="utilization-label">利用率</div>
            <div className="utilization-value">{utilizationRate}%</div>
          </div>
        </div>

        {/* 采购建议 */}
        {currentAsset.available_quantity <= currentAsset.minimum_stock && (
          <div className="detail-section">
            <h3>采购建议</h3>
            <div className="purchase-alert">
              <div className="alert-icon"><AlertTriangle size={24} color="#D4952B" /></div>
              <div className="alert-content">
                <div className="alert-title">
                  {currentAsset.available_quantity === 0 ? '库存已耗尽' : '库存不足'}
                </div>
                <div className="alert-message">
                  建议采购 {Math.max(currentAsset.minimum_stock * 2 - currentAsset.available_quantity, currentAsset.minimum_stock)} 个，
                  以维持正常库存水平
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 备注 */}
        {currentAsset.notes && (
          <div className="detail-section">
            <h3>备注</h3>
            <div className="notes-content">
              {currentAsset.notes}
            </div>
          </div>
        )}

        {/* 操作历史 */}
        <div className="detail-section">
          <h3>操作历史</h3>
          {logsLoading ? (
            <div style={{ textAlign: 'center', padding: '20px', color: '#8E9EA4' }}>加载中...</div>
          ) : warehouseLogs.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '20px', color: '#8E9EA4' }}>暂无操作记录</div>
          ) : (
            <div className="history-list">
              {warehouseLogs.map(log => (
                <div key={log.id} className="history-item update">
                  <div className="history-header">
                    <span className="history-action">{log.action}</span>
                    <span className="history-time">{new Date(log.created_at).toLocaleString('zh-CN')}</span>
                  </div>
                  {log.operator && (
                    <div className="history-operator">操作人: {log.operator}</div>
                  )}
                  {log.description && (
                    <div className="history-changes">
                      {log.description.split('; ').map((change, i) => (
                        <div key={i} className="history-change-item">{change}</div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="warehouse-detail-actions">
        {isReadOnly ? (
          <div style={{color: '#8e9ea4', fontSize: 13, width: '100%', textAlign: 'center'}}>
            只读模式：仅供查看
          </div>
        ) : (
          <>
            <button className="btn btn-primary" onClick={handleEdit} disabled={loading}>
              编辑物料
            </button>
            <button
              className="btn btn-success"
              onClick={handleAssign}
              disabled={loading || currentAsset.available_quantity <= 0}
            >
              领用出库
            </button>
            {isAdmin && (
              <button className="btn btn-danger" onClick={() => setShowDeleteModal(true)} disabled={loading}>
                删除物料
              </button>
            )}
          </>
        )}
      </div>

      {/* 领用出库弹窗 */}
      {showAssignModal && (
        <div className="modal-overlay" onClick={() => setShowAssignModal(false)}>
          <div className="modal-content scrollable-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>领用出库 - {currentAsset.name}</h2>
              <button className="close-btn" onClick={() => setShowAssignModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleAssignSubmit}>
              <div className="modal-body scrollable-modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label>领用数量 *</label>
                    <input
                      type="number"
                      value={assignData.assign_quantity}
                      onChange={(e) => setAssignData({...assignData, assign_quantity: parseInt(e.target.value) || 1})}
                      min="1"
                      max={currentAsset.available_quantity}
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>物料名称</label>
                    <input
                      type="text"
                      value={assignData.asset_display_name}
                      onChange={(e) => setAssignData({...assignData, asset_display_name: e.target.value})}
                      placeholder="显示在操作记录中的名称"
                    />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>领用人</label>
                    <input
                      type="text"
                      value={assignData.employee_name}
                      onChange={(e) => setAssignData({...assignData, employee_name: e.target.value})}
                      placeholder="可选"
                    />
                  </div>
                  <div className="form-group">
                    <label>工号</label>
                    <input
                      type="text"
                      value={assignData.employee_id}
                      onChange={(e) => setAssignData({...assignData, employee_id: e.target.value})}
                      placeholder="可选"
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label>部门</label>
                  <select
                    value={assignData.department}
                    onChange={(e) => setAssignData({...assignData, department: e.target.value})}
                  >
                    <option value="">选择部门（可选）</option>
                    {departments.map(d => <option key={d.id} value={d.display}>{d.display}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label>备注</label>
                  <textarea
                    value={assignData.notes}
                    onChange={(e) => setAssignData({...assignData, notes: e.target.value})}
                    placeholder="可选，如领用用途等"
                    rows="3"
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAssignModal(false)}>取消</button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? '出库中...' : '确认领用'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 成功弹窗 */}
      {showSuccessModal && (
        <div className="modal-overlay" onClick={() => setShowSuccessModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header success">
              <h2>领用成功</h2>
              <button className="close-btn" onClick={() => setShowSuccessModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="success-icon"><CheckCircle size={48} color="#3A9E75" /></div>
              <p>{successMessage}</p>
              <p style={{ color: '#8E9EA4', fontSize: '14px', marginTop: '10px' }}>
                库存数量已更新，本次领用不会创建固定资产记录
              </p>
            </div>
            <div className="modal-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setShowSuccessModal(false)}
              >
                继续管理
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      {showDeleteModal && (
        <div className="modal-overlay" onClick={() => setShowDeleteModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header danger">
              <h2>删除确认</h2>
              <button className="close-btn" onClick={() => setShowDeleteModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <p>确定要删除库房资产 "{currentAsset.name}" 吗？</p>
              <p style={{ color: '#E05252', fontSize: '14px', marginTop: '10px' }}>
                此操作不可撤销
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowDeleteModal(false)}>取消</button>
              <button className="btn btn-danger" onClick={handleDelete} disabled={loading}>
                {loading ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default WarehouseAssetDetail