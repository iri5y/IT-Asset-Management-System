import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import {useAuth} from '../contexts/AuthContext'
import { X, AlertTriangle, CheckCircle } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

function WarehouseAssetDetail({ asset, onClose, onEdit, onDelete, onRefresh, onBackToHome, isAdmin }) {
  const {isReadOnly} = useAuth()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [successMessage, setSuccessMessage] = useState('')
  const [createdAssetId, setCreatedAssetId] = useState(null)
  const [warehouseLogs, setWarehouseLogs] = useState([])
  const [logsLoading, setLogsLoading] = useState(false)
  const [departments, setDepartments] = useState([])
  const [currentAsset, setCurrentAsset] = useState(asset)
  const [assignData, setAssignData] = useState({
    employee_name: '',
    employee_id: '',
    department: '',
    location: '',
    serial_number: '',
    mac_address: '',
    system_version: '',
    antivirus_software: '',
    lock_number: '',
    asset_category: '',
  })
  const [nextTagMap, setNextTagMap] = useState({})  // 品类 → 建议编号的缓存

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

  // 消耗品品类：非计算机设备、非移动设备，走简化分配流程（仅扣减库存，不创建资产记录）
  const DEVICE_CATEGORIES = ['计算机设备', '移动设备']
  const isConsumable = !DEVICE_CATEGORIES.includes(currentAsset?.category)

  const handleAssign = () => {
    setAssignData({
      employee_name: '',
      employee_id: '',
      department: '',
      location: '',
      serial_number: '',
      mac_address: '',
      system_version: '',
      antivirus_software: '',
      lock_number: '',
      assign_quantity: 1,
      asset_display_name: currentAsset.name,
      asset_category: '',
      notes: '',
    })
    setNextTagMap({})
    setShowAssignModal(true)
  }

  // 选择品类时，从后端获取该品类的下一个可用编号
  const handleCategoryChange = async (category) => {
    setAssignData(prev => ({ ...prev, asset_category: category }))
    if (!category) return
    if (nextTagMap[category]) return  // 已缓存，不重复请求
    try {
      const res = await axios.get(`${API_URL}/assets/next-tag/${encodeURIComponent(category)}`)
      setNextTagMap(prev => ({ ...prev, [category]: res.data.suggested_tag }))
    } catch (err) {
      console.error('获取资产编号失败:', err)
    }
  }

  const handleAssignSubmit = async (e) => {
    e.preventDefault()

    try {
      setLoading(true)
      const qty = parseInt(assignData.assign_quantity) || 1

      // 先从后端获取最新库存，防止并发导致超卖
      const freshResponse = await axios.get(`${API_URL}/warehouse/${currentAsset.id}`)
      const freshAsset = freshResponse.data

      if (qty > freshAsset.available_quantity) {
        alert(`可用库存不足，当前实际可用: ${freshAsset.available_quantity}`)
        setCurrentAsset(freshAsset)
        setLoading(false)
        return
      }

      // ── 消耗品分支：仅扣减库存，记录操作日志，不创建资产记录 ──
      if (isConsumable) {
        // 构造可读的分配说明，写入操作历史
        const dispatchParts = [`分配 ${qty} 个「${currentAsset.name}」`]
        if (assignData.employee_name) dispatchParts.push(`领用人: ${assignData.employee_name}`)
        if (assignData.employee_id) dispatchParts.push(`工号: ${assignData.employee_id}`)
        if (assignData.department) dispatchParts.push(`部门: ${assignData.department}`)
        if (assignData.notes) dispatchParts.push(`备注: ${assignData.notes}`)

        await axios.put(`${API_URL}/warehouse/${currentAsset.id}`, {
          available_quantity: freshAsset.available_quantity - qty,
          allocated_quantity: freshAsset.allocated_quantity + qty,
          dispatch_note: dispatchParts.join('，'),
        })

        // 刷新本地状态
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
        setCreatedAssetId(null)
        const recipientInfo = assignData.employee_name ? ` 给 ${assignData.employee_name}` : ''
        setSuccessMessage(`已成功分配 ${qty} 个 ${currentAsset.name}${recipientInfo}`)
        setShowSuccessModal(true)
        return
      }

      // ── 设备分支（计算机/移动设备）：扣减库存 + 创建资产记录 ──
      if (!assignData.employee_name.trim()) {
        alert('请输入员工姓名')
        setLoading(false)
        return
      }

      // 与后端 SN_REQUIRED_CATEGORIES 保持一致：{"笔记本电脑", "台式机", "服务器", "移动设备"}
      const SN_REQUIRED_CATEGORIES = ['笔记本电脑', '台式机', '服务器', '移动设备']
      const effectiveCategory = assignData.asset_category || currentAsset.category
      const isSnRequired = SN_REQUIRED_CATEGORIES.includes(effectiveCategory)
      const isMacRequired = ['笔记本电脑', '台式机'].includes(effectiveCategory)

      if (isSnRequired && !assignData.serial_number.trim()) {
        alert(`「${effectiveCategory}」必须填写序列号`)
        setLoading(false)
        return
      }
      if (isMacRequired && !assignData.mac_address.trim()) {
        alert(`「${effectiveCategory}」必须填写MAC地址`)
        setLoading(false)
        return
      }

      // 先扣减库存（后端有行锁保护），再创建资产记录
      await axios.put(`${API_URL}/warehouse/${currentAsset.id}`, {
        available_quantity: freshAsset.available_quantity - qty,
        allocated_quantity: freshAsset.allocated_quantity + qty
      })

      let lastCreatedAsset = null
      const createdAssets = []

      try {
        for (let i = 0; i < qty; i++) {
          const baseTag = nextTagMap[assignData.asset_category]
          let assetTag
          if (baseTag) {
            const tagMatch = baseTag.match(/^(ZS-[A-Za-z0-9]{4}-)(\d{6})$/)
            if (tagMatch) {
              const tagNum = parseInt(tagMatch[2]) + i
              assetTag = `${tagMatch[1]}${String(tagNum).padStart(6, '0')}`
            } else {
              assetTag = baseTag
            }
          } else {
            assetTag = `ZS-WH${String(currentAsset.id).padStart(2,'0')}-${String(Date.now() + i).slice(-6)}`
          }

          const newAssetData = {
            asset_tag: assetTag,
            category: assignData.asset_category || currentAsset.category,
            brand: currentAsset.brand || '',
            model: currentAsset.model || '',
            hostname: assignData.asset_display_name || currentAsset.name,
            status: '使用中',
            employee_id: assignData.employee_id,
            employee_name: assignData.employee_name,
            department: assignData.department,
            location: assignData.location,
            quantity: 1,
            issue_date: new Date().toISOString(),
            notes: assignData.notes
              ? `从库房资产 ${currentAsset.name} 分配，备注: ${assignData.notes}`
              : `从库房资产 ${currentAsset.name} 分配`,
            from_warehouse: true,
          }
          if (assignData.serial_number?.trim()) newAssetData.serial_number = assignData.serial_number.trim() + (qty > 1 ? `-${i+1}` : '')
          if (assignData.mac_address?.trim()) newAssetData.mac_address = assignData.mac_address.trim()
          if (assignData.system_version?.trim()) newAssetData.system_version = assignData.system_version.trim()
          if (assignData.antivirus_software?.trim()) newAssetData.antivirus_software = assignData.antivirus_software.trim()
          if (assignData.lock_number?.trim()) newAssetData.lock_number = assignData.lock_number.trim()

          const createResponse = await axios.post(`${API_URL}/assets/`, newAssetData)
          lastCreatedAsset = createResponse.data
          createdAssets.push(createResponse.data)
        }
      } catch (assetError) {
        const successfullyCreated = createdAssets.length
        console.error(`创建资产记录失败（已创建 ${successfullyCreated}/${qty} 条），回滚库存:`, assetError)
        try {
          await axios.put(`${API_URL}/warehouse/${currentAsset.id}`, {
            available_quantity: freshAsset.available_quantity - successfullyCreated,
            allocated_quantity: freshAsset.allocated_quantity + successfullyCreated
          })
        } catch (rollbackError) {
          console.error('库存回滚失败，请手动检查:', rollbackError)
        }
        throw assetError
      }

      // 刷新本地状态
      try {
        const updatedResponse = await axios.get(`${API_URL}/warehouse/${currentAsset.id}`)
        setCurrentAsset(updatedResponse.data)
      } catch {
        setCurrentAsset({
          ...currentAsset,
          available_quantity: freshAsset.available_quantity - qty,
          allocated_quantity: freshAsset.allocated_quantity + qty
        })
      }

      if (onRefresh) onRefresh()
      setShowAssignModal(false)
      setCreatedAssetId(lastCreatedAsset.id)
      setSuccessMessage(`已成功分配 ${qty} 个 ${currentAsset.name} 给 ${assignData.employee_name}！`)
      setShowSuccessModal(true)

    } catch (error) {
      console.error('分配资产失败:', error)
      alert('分配资产失败: ' + (error.response?.data?.detail || error.message))
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
          编辑资产
         </button>
         <button 
          className="btn btn-success" 
          onClick={handleAssign} 
          disabled={loading || currentAsset.available_quantity <= 0}
         >
          分配资产
         </button>
         {isAdmin && (
           <button className="btn btn-danger" onClick={() => setShowDeleteModal(true)} disabled={loading}>
            删除资产
           </button>
          )}
        </>
        )}
      </div>

      {/* 分配资产弹窗 */}
      {showAssignModal && (
        <div className="modal-overlay" onClick={() => setShowAssignModal(false)}>
          <div className="modal-content scrollable-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>分配资产 - {currentAsset.name}</h2>
              <button className="close-btn" onClick={() => setShowAssignModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleAssignSubmit}>
              <div className="modal-body scrollable-modal-body">

                {/* ── 消耗品简化表单 ── */}
                {isConsumable ? (
                  <>
                    <div className="form-row">
                      <div className="form-group">
                        <label>分配数量 *</label>
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
                        <label>资产名称</label>
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
                        <label>员工姓名</label>
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
                  </>
                ) : (
                  /* ── 设备完整表单（计算机/移动设备）── */
                  <>
                    <div className="form-row">
                      <div className="form-group">
                        <label>分配数量 *</label>
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
                        <label>资产名称</label>
                        <input
                          type="text"
                          value={assignData.asset_display_name}
                          onChange={(e) => setAssignData({...assignData, asset_display_name: e.target.value})}
                          placeholder="显示在资产列表中的名称"
                        />
                      </div>
                    </div>
                    {/* 资产品类：将库房大类细化为具体资产品类 */}
                    <div className="form-group">
                      <label>资产品类 *</label>
                      <select
                        value={assignData.asset_category}
                        onChange={(e) => handleCategoryChange(e.target.value)}
                        required
                      >
                        <option value="">选择具体品类</option>
                        {currentAsset.category === '计算机设备' && <>
                          <option value="台式机">台式机</option>
                          <option value="笔记本电脑">笔记本电脑</option>
                        </>}
                        {currentAsset.category === '移动设备' && <>
                          <option value="移动设备">移动设备（PAD）</option>
                          <option value="手机">手机</option>
                        </>}
                        {!['计算机设备','移动设备'].includes(currentAsset.category) && (
                          <option value={currentAsset.category}>{currentAsset.category}</option>
                        )}
                      </select>
                      {assignData.asset_category && nextTagMap[assignData.asset_category] && (
                        <div style={{
                          marginTop: 6, padding: '6px 10px',
                          background: '#EBF0F8', borderRadius: 6,
                          fontSize: 12, color: '#375B81', fontWeight: 500,
                        }}>
                          将生成编号：
                          <span style={{ fontFamily: 'monospace', marginLeft: 4 }}>
                            {(() => {
                              const base = nextTagMap[assignData.asset_category]
                              const qty = parseInt(assignData.assign_quantity) || 1
                              if (qty <= 1) return base
                              const m = base.match(/^(ZS-[A-Za-z0-9]{4}-)(\d{6})$/)
                              if (!m) return base
                              const end = parseInt(m[2]) + qty - 1
                              return `${base} ~ ${m[1]}${String(end).padStart(6,'0')}`
                            })()}
                          </span>
                        </div>
                      )}
                      {assignData.asset_category && !nextTagMap[assignData.asset_category] && (
                        <div style={{ marginTop: 6, fontSize: 12, color: '#8E9EA4' }}>正在获取编号...</div>
                      )}
                    </div>
                    <div className="form-group">
                      <label>员工姓名 *</label>
                      <input
                        type="text"
                        value={assignData.employee_name}
                        onChange={(e) => setAssignData({...assignData, employee_name: e.target.value})}
                        placeholder="请输入员工姓名"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label>工号</label>
                      <input
                        type="text"
                        value={assignData.employee_id}
                        onChange={(e) => setAssignData({...assignData, employee_id: e.target.value})}
                        placeholder="请输入工号（可选）"
                      />
                    </div>
                    <div className="form-group">
                      <label>部门</label>
                      <select
                        value={assignData.department}
                        onChange={(e) => setAssignData({...assignData, department: e.target.value})}
                      >
                        <option value="">选择部门</option>
                        {departments.map(d => <option key={d.id} value={d.display}>{d.display}</option>)}
                      </select>
                    </div>
                    <div className="form-group">
                      <label>资产位置</label>
                      <input
                        type="text"
                        value={assignData.location}
                        onChange={(e) => setAssignData({...assignData, location: e.target.value})}
                        placeholder="请输入资产位置（可选）"
                      />
                    </div>
                    <div className="form-group">
                      <label>备注</label>
                      <textarea
                        value={assignData.notes}
                        onChange={(e) => setAssignData({...assignData, notes: e.target.value})}
                        placeholder="可选"
                        rows="2"
                      />
                    </div>
                    {/* 序列号：笔记本电脑、台式机、服务器、移动设备必填 */}
                    {['笔记本电脑', '台式机', '服务器', '移动设备'].includes(assignData.asset_category) && (
                      <div className="form-group">
                        <label>序列号 *</label>
                        <input
                          type="text"
                          value={assignData.serial_number}
                          onChange={(e) => setAssignData({...assignData, serial_number: e.target.value})}
                          placeholder="请输入序列号"
                          required
                        />
                      </div>
                    )}
                    {/* MAC地址、系统版本等：仅台式机和笔记本电脑需要 */}
                    {['笔记本电脑', '台式机'].includes(assignData.asset_category) && (
                      <>
                        <div className="form-group">
                          <label>MAC地址 *</label>
                          <input
                            type="text"
                            value={assignData.mac_address}
                            onChange={(e) => setAssignData({...assignData, mac_address: e.target.value})}
                            placeholder="请输入MAC地址"
                            required
                          />
                        </div>
                        <div className="form-group">
                          <label>系统版本</label>
                          <input
                            type="text"
                            value={assignData.system_version}
                            onChange={(e) => setAssignData({...assignData, system_version: e.target.value})}
                            placeholder="请输入系统版本（可选）"
                          />
                        </div>
                        <div className="form-group">
                          <label>杀毒软件</label>
                          <input
                            type="text"
                            value={assignData.antivirus_software}
                            onChange={(e) => setAssignData({...assignData, antivirus_software: e.target.value})}
                            placeholder="请输入杀毒软件（可选）"
                          />
                        </div>
                        <div className="form-group">
                          <label>锁号</label>
                          <input
                            type="text"
                            value={assignData.lock_number}
                            onChange={(e) => setAssignData({...assignData, lock_number: e.target.value})}
                            placeholder="请输入锁号（可选）"
                          />
                        </div>
                      </>
                    )}
                  </>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowAssignModal(false)}>取消</button>
                <button type="submit" className="btn btn-primary" disabled={loading}>
                  {loading ? '分配中...' : '确认分配'}
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
              <h2>分配成功</h2>
              <button className="close-btn" onClick={() => setShowSuccessModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="success-icon"><CheckCircle size={48} color="#3A9E75" /></div>
              <p>{successMessage}</p>
              {isConsumable ? (
                <p style={{ color: '#8E9EA4', fontSize: '14px', marginTop: '10px' }}>
                  库存数量已更新
                </p>
              ) : (
                <p style={{ color: '#8E9EA4', fontSize: '14px', marginTop: '10px' }}>
                  您可以选择查看新创建的资产详情或继续管理库房资产
                </p>
              )}
            </div>
            <div className="modal-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setShowSuccessModal(false)}
              >
                继续管理
              </button>
              {!isConsumable && createdAssetId && (
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setShowSuccessModal(false)
                    navigate('/assets')
                    setTimeout(() => {
                      window.dispatchEvent(new CustomEvent('selectAsset', {
                        detail: { assetId: createdAssetId }
                      }))
                    }, 500)
                  }}
                >
                  查看资产详情
                </button>
              )}
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