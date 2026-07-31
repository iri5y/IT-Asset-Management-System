import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { X, Plus, Trash2, Wrench, Archive } from 'lucide-react'
import {useAuth} from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''

function AssetDetail({ asset, onClose, onEdit, onRefresh, isAdmin }) {
  const {isReadOnly} = useAuth()
  const navigate = useNavigate()
  const [logs, setLogs] = useState([])
  const [hostnameHistory, setHostnameHistory] = useState([])
  const [loading, setLoading] = useState(true)
  // 配件记录
  const [partLogs, setPartLogs] = useState([])
  const [showPartModal, setShowPartModal] = useState(false)
  const [warehouseItems, setWarehouseItems] = useState([])
  const [officelocations, setOfficeLocations] = useState([])
  const [partForm, setPartForm] = useState({
    warehouse_item_id: '',
    warehouse_item_name: '',
    action: '新增',
    quantity: 1,
    notes: '',
  })

  useEffect(() => {
    if (asset) {
      fetchLogs()
      fetchHostnameHistory()
      fetchPartLogs()
    }
  }, [asset])

  useEffect(() => {
    axios.get(`${API_URL}/locations/`).then(res => setLocations(res.data)).catch(() => {})
    axios.get(`${API_URL}/office-locations/`).then(res => setOfficeLocations(res.data)).catch(() => {})
    axios.get(`${API_URL}/departments/flat`).then(res => setDepartments(res.data)).catch(() => {})
    // 加载库房配件列表（用于配件弹窗下拉）
    axios.get(`${API_URL}/warehouse/`).then(res => setWarehouseItems(res.data)).catch(() => {})
  }, [])

  const fetchLogs = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_URL}/assets/${asset.id}/logs`)
      setLogs(response.data)
    } catch (error) {
      console.error('获取日志失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchHostnameHistory = async () => {
    try {
      const response = await axios.get(`${API_URL}/assets/${asset.id}/hostname-history`)
      setHostnameHistory(response.data)
    } catch (error) {
      console.error('获取主机名历史失败:', error)
    }
  }

  const fetchPartLogs = async () => {
    try {
      const response = await axios.get(`${API_URL}/assets/${asset.id}/parts`)
      setPartLogs(response.data)
    } catch (error) {
      console.error('获取配件记录失败:', error)
    }
  }

  const handleOpenPartModal = () => {
    setPartForm({ warehouse_item_id: '', warehouse_item_name: '', action: '新增', quantity: 1, notes: '' })
    setShowPartModal(true)
  }

  const handlePartWarehouseSelect = (e) => {
    const id = e.target.value
    if (!id) {
      setPartForm(prev => ({ ...prev, warehouse_item_id: '', warehouse_item_name: '' }))
      return
    }
    const item = warehouseItems.find(w => String(w.id) === id)
    setPartForm(prev => ({
      ...prev,
      warehouse_item_id: id,
      warehouse_item_name: item ? `${item.name}${item.brand ? ' ' + item.brand : ''}${item.model ? ' ' + item.model : ''}` : '',
    }))
  }

  const handlePartSubmit = async (e) => {
    e.preventDefault()
    if (!partForm.warehouse_item_name.trim()) {
      alert('请填写配件名称')
      return
    }
    if (partForm.quantity <= 0) {
      alert('数量必须大于 0')
      return
    }
    try {
      await axios.post(`${API_URL}/assets/${asset.id}/parts`, {
        warehouse_item_id: partForm.warehouse_item_id ? Number(partForm.warehouse_item_id) : null,
        warehouse_item_name: partForm.warehouse_item_name.trim(),
        action: partForm.action,
        quantity: Number(partForm.quantity),
        notes: partForm.notes.trim() || null,
      })
      setShowPartModal(false)
      fetchPartLogs()
      fetchLogs()
    } catch (error) {
      alert('添加失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const handleDeletePart = async (partId) => {
    if (!window.confirm('确定要删除此配件记录？库房库存将自动回滚。')) return
    try {
      await axios.delete(`${API_URL}/assets/${asset.id}/parts/${partId}`)
      fetchPartLogs()
      fetchLogs()
    } catch (error) {
      alert('删除失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString('zh-CN')
  }

  const [showAssignModal, setShowAssignModal] = useState(false)
  const [showStorageModal, setShowStorageModal] = useState(false)
  const [showRetireModal, setShowRetireModal] = useState(false)
  const [storageReason, setStorageReason] = useState('')
  const [storageLocation, setStorageLocation] = useState('')
  const [storageCondition, setStorageCondition] = useState('可用')
  const [locations, setLocations] = useState([])
  const [departments, setDepartments] = useState([])
  const [retireReason, setRetireReason] = useState('')

  // 资产状况颜色配置
  const CONDITION_STYLE = {
    '可用':   { bg: '#d1fae5', color: '#065f46', border: '#6ee7b7' },
    '损坏':   { bg: '#ffedd5', color: '#9a3412', border: '#fdba74' },
    '待报废': { bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
  }
  const [editingHostname, setEditingHostname] = useState(false)
  const [hostnameInput, setHostnameInput] = useState('')
  const [assignData, setAssignData] = useState({
    employee_name: '',
    employee_id: '',
    department: '',
    supervisor: '',
    hostname: '',
    location: '',
    assign_reason: ''
  })

  const handleAssign = () => {
    setAssignData({
      employee_name: asset.employee_name || '',
      employee_id: asset.employee_id || '',
      department: asset.department || '',
      supervisor: asset.supervisor || '',
      hostname: asset.hostname || '',
      location: asset.location || '',
      assign_reason: ''
    })
    setShowAssignModal(true)
  }

  const handleAssignSubmit = async (e) => {
    e.preventDefault()
    if (!assignData.employee_name.trim()) {
      alert('请输入员工姓名')
      return
    }
    if (!assignData.employee_id.trim()) {
      alert('请输入工号')
      return
    }
    if (!assignData.department.trim()) {
      alert('请输入部门')
      return
    }
    try {
      await axios.put(`${API_URL}/assets/${asset.id}`, {
        employee_name: assignData.employee_name.trim(),
        employee_id: assignData.employee_id.trim(),
        department: assignData.department.trim(),
        supervisor: assignData.supervisor.trim(),
        hostname: assignData.hostname.trim(),
        location: assignData.location.trim(),
        status: '使用中',
        issue_date: new Date().toISOString(),
        notes: assignData.assign_reason.trim() ? `分配原因: ${assignData.assign_reason.trim()}` : asset.notes
      })
      setShowAssignModal(false)
      await onRefresh()
      fetchLogs()
    } catch (error) {
      alert('分配失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const handleRetire = () => {
    setRetireReason('')
    setShowRetireModal(true)
  }

  const handleRetireConfirm = async () => {
    if (!retireReason.trim()) {
      alert('请输入报废原因')
      return
    }
    try {
      await axios.put(`${API_URL}/assets/${asset.id}`, {
        status: '报废',
        employee_name: '',
        employee_id: '',
        department: '',
        notes: `报废原因: ${retireReason.trim()}`
      })
      setShowRetireModal(false)
      await onRefresh()
      fetchLogs()
    } catch (error) {
      alert('报废失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const handleStorage = () => {
    setStorageReason('')
    setStorageLocation('')
    setStorageCondition('可用')
    setShowStorageModal(true)
  }

  const handleStorageConfirm = async () => {
    if (!storageLocation) {
      alert('请选择入库位置')
      return
    }
    if (!storageReason.trim()) {
      alert('请输入入库原因')
      return
    }
    // 损坏或待报废时备注必填（已由上面校验覆盖，此处额外提示）
    if ((storageCondition === '损坏' || storageCondition === '待报废') && !storageReason.trim()) {
      alert(`资产状况为「${storageCondition}」时，备注原因为必填项`)
      return
    }
    try {
      await axios.put(`${API_URL}/assets/${asset.id}`, {
        status: '闲置',
        condition: storageCondition,
        employee_name: '',
        employee_id: '',
        department: '',
        location: storageLocation,
        notes: storageReason.trim(),
      })
      setShowStorageModal(false)
      await onRefresh()
      fetchLogs()
    } catch (error) {
      alert('入库失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const handleHostnameSave = async () => {
    const trimmed = hostnameInput.trim()
    if (trimmed === (asset.hostname || '')) {
      setEditingHostname(false)
      return
    }
    try {
      await axios.put(`${API_URL}/assets/${asset.id}`, { hostname: trimmed })
      setEditingHostname(false)
      await onRefresh()
      fetchLogs()
    } catch (error) {
      alert('修改资产名失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const getActionType = (action) => {
    if (action.includes('创建') || action.includes('create')) return 'create'
    if (action.includes('删除') || action.includes('delete')) return 'delete'
    if (action.includes('状态变更')) return 'update'
    return 'update'
  }

  const isDesktop = asset.category === '台式机'
  const isLaptop = asset.category === '笔记本电脑'
  const isComputer = isDesktop || isLaptop
  const isRetired = asset.status === '报废'

  return (
    <div className="asset-detail-panel">
      {/* Header with editable name */}
      <div className="detail-header">
        <div className="hostname-editable">
          {editingHostname ? (
            <input
              className="hostname-edit-input"
              value={hostnameInput}
              onChange={(e) => setHostnameInput(e.target.value)}
              onBlur={handleHostnameSave}
              onKeyDown={(e) => { if (e.key === 'Enter') handleHostnameSave(); if (e.key === 'Escape') setEditingHostname(false); }}
              autoFocus
            />
          ) : (
            <h2
              onClick={(isRetired || isReadOnly)? undefined : () => { setHostnameInput(asset.hostname || asset.asset_tag || ''); setEditingHostname(true); }}
              title={(isRetired || isReadOnly)? undefined : '点击修改名称'}
              style={(isRetired || isReadOnly) ? { cursor: 'default' } : {}}
            >
              {asset.hostname || asset.asset_tag}
            </h2>
          )}
          <span className={`status-badge status-${asset.status.replace(/\s+/g, '-')}`}>{asset.status}</span>
        </div>
        <div className="detail-header-actions">
          <button className="close-detail-btn" onClick={() => { onClose(); navigate('/'); }} title="返回资产看板">
            <X size={18} />
          </button>
        </div>
      </div>

      <div className="detail-content-wrapper">
        <div className="detail-card main-detail">

        {/* ===== 资产信息 ===== */}
        <div className="detail-info-block">
          <div className="detail-section-label">资产信息</div>
          <div className="detail-grid compact">
            <div className="detail-item">
              <div className="detail-label">资产编号</div>
              <div className="detail-value font-data">{asset.asset_tag}</div>
            </div>
            <div className="detail-item">
              <div className="detail-label">品类</div>
              <div className="detail-value">{asset.category}</div>
            </div>
            <div className="detail-item">
              <div className="detail-label">品牌</div>
              <div className="detail-value">{asset.brand || '-'}</div>
            </div>
            <div className="detail-item">
              <div className="detail-label">型号</div>
              <div className="detail-value">{asset.model || '-'}</div>
            </div>
            <div className="detail-item">
              <div className="detail-label">序列号</div>
              <div className="detail-value font-data">{asset.serial_number || '-'}</div>
            </div>
            <div className="detail-item">
              <div className="detail-label">状态</div>
              <div className="detail-value">
                <span className={`status-badge status-${asset.status.replace(' ', '-')}`}>{asset.status}</span>
              </div>
            </div>
            {asset.location && (
              <div className="detail-item">
                <div className="detail-label">位置</div>
                <div className="detail-value">{asset.location}</div>
              </div>
            )}
            {/* 新展示资产PO号 */}
            <div className='detail-item'>
              <div className='detail-label'>PO号</div>
              <div className='detail-value'>
                {asset?.po_number || '暂无'}
              </div>
            </div>
          </div>
        </div>


        {/* ===== 设备信息（有数据即显示，不限品类）===== */}
        {(asset.mac_address || asset.ip_address || asset.system_version ||
          asset.antivirus_software || asset.lock_number ||
          asset.bios_password || asset.tpm_status || asset.has_desktop) && (
          <div className="detail-info-block">
            <div className="detail-section-label">设备信息</div>
            <div className="detail-grid compact">
              {asset.mac_address && <div className="detail-item"><div className="detail-label">MAC地址</div><div className="detail-value font-data">{asset.mac_address}</div></div>}
              {asset.ip_address && <div className="detail-item"><div className="detail-label">IP地址</div><div className="detail-value font-data">{asset.ip_address}</div></div>}
              {asset.system_version && <div className="detail-item"><div className="detail-label">系统版本</div><div className="detail-value">{asset.system_version}</div></div>}
              {asset.antivirus_software && <div className="detail-item"><div className="detail-label">杀毒软件</div><div className="detail-value">{asset.antivirus_software}</div></div>}
              {asset.lock_number && <div className="detail-item"><div className="detail-label">锁号</div><div className="detail-value font-data">{asset.lock_number}</div></div>}
              {isLaptop && <div className="detail-item"><div className="detail-label">BIOS密码</div><div className="detail-value">{asset.bios_password ? '已开启' : '未开启'}</div></div>}
              {isLaptop && <div className="detail-item"><div className="detail-label">TPM状态</div><div className="detail-value">{asset.tpm_status ? '已开启' : '未开启'}</div></div>}
              {isLaptop && <div className="detail-item"><div className="detail-label">是否有台式机</div><div className="detail-value">{asset.has_desktop ? '是' : '否'}</div></div>}
            </div>
          </div>
        )}

        {/* ===== 配件记录（仅台式机和笔记本）===== */}
        {isComputer && (
          <div className="detail-info-block">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div className="detail-section-label" style={{ marginBottom: 0 }}>
                <Wrench size={13} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                配件记录
              </div>
              {!isReadOnly && <button
                className="btn btn-sm btn-primary"
                onClick={handleOpenPartModal}
                style={{ fontSize: 12, padding: '3px 10px', gap: 4 }}
              >
                <Plus size={12} /> 添加配件
              </button>}
            </div>
            {partLogs.length === 0 ? (
              <div style={{ fontSize: 13, color: 'var(--color-muted)', padding: '8px 0' }}>暂无配件记录</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {partLogs.map(p => (
                  <div key={p.id} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                    padding: '8px 10px', background: 'var(--color-bg)',
                    border: '1px solid var(--color-border)', borderRadius: 6, fontSize: 13,
                  }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 2 }}>
                        <span style={{
                          padding: '1px 7px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                          background: p.action === '新增' ? '#d1fae5' : '#dbeafe',
                          color: p.action === '新增' ? '#065f46' : '#1e40af',
                        }}>
                          {p.action}
                        </span>
                        <span style={{ fontWeight: 500 }}>{p.warehouse_item_name}</span>
                        <span style={{ color: 'var(--color-muted)' }}>× {p.quantity}</span>
                      </div>
                      {p.notes && <div style={{ color: 'var(--color-muted)', fontSize: 12 }}>{p.notes}</div>}
                      <div style={{ color: 'var(--color-muted)', fontSize: 11, marginTop: 2 }}>
                        {p.operator && <span>{p.operator} · </span>}
                        {new Date(p.created_at).toLocaleString('zh-CN')}
                      </div>
                    </div>
                    {isAdmin && (
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => handleDeletePart(p.id)}
                        title="删除记录并回滚库存"
                        style={{ marginLeft: 8, flexShrink: 0 }}
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ===== 使用人信息 ===== */}
        {asset.employee_name && (          <div className="detail-info-block">
            <div className="detail-section-label">使用人信息</div>
            <div className="detail-grid compact">
              <div className="detail-item"><div className="detail-label">使用人</div><div className="detail-value">{asset.employee_name}</div></div>
              <div className="detail-item"><div className="detail-label">工号</div><div className="detail-value">{asset.employee_id}</div></div>
              <div className="detail-item"><div className="detail-label">部门</div><div className="detail-value">{asset.department || '-'}</div></div>
              <div className="detail-item"><div className="detail-label">直属领导</div><div className="detail-value">{asset.supervisor || '-'}</div></div>
            </div>
          </div>
        )}

        {asset.notes && (
          <div className="detail-item" style={{ marginTop: '8px' }}>
            <div className="detail-label">备注</div>
            <div className="detail-value">{asset.notes}</div>
          </div>
        )}

        {/* 报废状态：显示只读提示，不显示任何操作按钮 */}
        {isRetired ? (
          <div style={{
            marginTop: 16,
            padding: '12px 16px',
            background: '#F1F5F9',
            border: '1px solid #CBD5E1',
            borderRadius: 8,
            fontSize: 13,
            color: '#475569',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <Archive size={16} style={{ color: '#475569', flexShrink: 0 }} />
            此资产已报废，不可进行任何操作
          </div>
        ) : isReadOnly ? (
          <div style={{
            marginTop:16, padding:'12px 16px', background:'#f8fafc', border:'1px',
            borderRadius:8, fontSize:13, color:'#64748b', textAlign:'center'
          }}>
            您当前为只读权限，仅可查看资产信息
          </div>
        ): (
          <div className="action-buttons">
            {!isReadOnly && (
              <>
              <button className="btn btn-edit" onClick={() => onEdit(asset)}>编辑信息</button>
              <button className="btn btn-primary" onClick={handleAssign}>{asset.employee_name ? '重新分配' : '分配给个人'}</button>
              {asset.status === '使用中' && <button className="btn btn-secondary" onClick={handleStorage}>入库</button>}
              {isAdmin && <button className="btn btn-danger" onClick={handleRetire}>报废</button>}
              </>
            )}
          </div>
        )}
        </div>

        {/* 右侧操作历史卡片 */}
        <div className="detail-card history-card">
          {/* 资产名变更历史 */}
          {hostnameHistory.length > 0 && (
            <div className="history-section">
              <h3>资产名变更历史</h3>
              <div className="history-list">
                {hostnameHistory.map(history => (
                  <div key={history.id} className="history-item update">
                    <div className="history-header">
                      <span className="history-action">资产名变更</span>
                      <span className="history-time">{formatDate(history.changed_at)}</span>
                    </div>
                    <div className="history-description">
                      <strong>从:</strong> {history.old_hostname} <strong>→</strong> {history.new_hostname}
                    </div>
                    {history.change_reason && (
                      <div className="history-description">
                        <strong>原因:</strong> {history.change_reason}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="history-section">
            <h3>操作历史</h3>
            {loading ? (
              <div style={{ textAlign: 'center', padding: '20px', color: '#999' }}>
                加载中...
              </div>
            ) : logs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '20px', color: '#999' }}>
                暂无操作记录
              </div>
            ) : (
              <div className="history-list">
                {logs.map(log => (
                  <div key={log.id} className={`history-item ${getActionType(log.action)}`}>
                    <div className="history-header">
                      <span className="history-action">{log.action}</span>
                      <span className="history-time">{formatDate(log.created_at)}</span>
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
      </div>

      {/* 分配给个人弹窗 */}
      {showAssignModal && (
        <div className="modal-overlay" onClick={() => setShowAssignModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>分配给个人</h2>
              <button className="close-btn" onClick={() => setShowAssignModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleAssignSubmit}>
              <div className="modal-body">
                <div className="form-row">
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
                    <label>工号 *</label>
                    <input 
                      type="text" 
                      value={assignData.employee_id}
                      onChange={(e) => setAssignData({...assignData, employee_id: e.target.value})}
                      placeholder="请输入工号"
                      required
                    />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>部门 *</label>
                    <select
                      value={assignData.department}
                      onChange={(e) => setAssignData({...assignData, department: e.target.value})}
                      required
                    >
                      <option value="">选择部门</option>
                      {departments.map(d => <option key={d.id} value={d.display}>{d.display}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label>直属领导</label>
                    <input 
                      type="text" 
                      value={assignData.supervisor}
                      onChange={(e) => setAssignData({...assignData, supervisor: e.target.value})}
                      placeholder="请输入直属领导（可选）"
                    />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label>资产名</label>
                    <input 
                      type="text" 
                      value={assignData.hostname}
                      onChange={(e) => setAssignData({...assignData, hostname: e.target.value})}
                      placeholder="请输入资产名（可选）"
                    />
                  </div>
                  <div className="form-group">
                    <label>资产位置</label>
                    <select 
                      value={assignData.officelocation}
                      onChange={(e) => setAssignData({...assignData, officelocation: e.target.value})}
                    >
                     <option value="">选择资产位置（可选）</option>
                     {officelocations.map(loc => (<option key={loc.id} value={loc.name}>{loc.name}</option>
                     ))}
                  </select>
                </div>
                  
                </div>
                <div className="form-group">
                  <label>分配原因</label>
                  <textarea 
                    value={assignData.assign_reason}
                    onChange={(e) => setAssignData({...assignData, assign_reason: e.target.value})}
                    placeholder="请输入分配原因（可选）"
                    rows="2"
                  />
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

      {/* 入库确认弹窗 */}
      {showStorageModal && (
        <div className="modal-overlay" onClick={() => setShowStorageModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>入库确认</h2>
              <button className="close-btn" onClick={() => setShowStorageModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <p>确定要将此资产入库吗？</p>
              <p style={{ color: '#8E9EA4', fontSize: '13px', marginTop: '8px', marginBottom: '16px' }}>
                入库后将清除员工分配信息，资产状态将变更为"闲置"
              </p>

              {/* 入库位置 */}
              <div className="form-group">
                <label>入库位置 *</label>
                <select value={storageLocation} onChange={(e) => setStorageLocation(e.target.value)} required>
                  <option value="">选择入库位置</option>
                  {locations && locations.map(loc => (
                    <option key={loc.id} value={loc.name}>{loc.name}</option>
                  ))}
                </select>
              </div>

              {/* 资产状况选择 */}
              <div className="form-group">
                <label>
                  资产状况 *
                  <span style={{ fontSize: 12, color: 'var(--color-muted)', marginLeft: 6, fontWeight: 400 }}>
                    （损坏或待报废时备注必填）
                  </span>
                </label>
                <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
                  {['可用', '损坏', '待报废'].map(cond => {
                    const cfg = CONDITION_STYLE[cond]
                    const selected = storageCondition === cond
                    return (
                      <button
                        key={cond}
                        type="button"
                        onClick={() => { setStorageCondition(cond); setStorageReason('') }}
                        style={{
                          padding: '6px 16px',
                          borderRadius: 6,
                          border: `2px solid ${selected ? cfg.border : 'var(--color-border)'}`,
                          background: selected ? cfg.bg : '#fff',
                          color: selected ? cfg.color : 'var(--color-body)',
                          fontWeight: selected ? 700 : 400,
                          fontSize: 13,
                          cursor: 'pointer',
                          transition: 'all 0.15s',
                        }}
                      >
                        {cond}
                      </button>
                    )
                  })}
                </div>
              </div>

              {/* 备注：损坏/待报废必填，可用可选 */}
              <div className="form-group">
                <label>
                  入库备注
                  {(storageCondition === '损坏' || storageCondition === '待报废') && (
                    <span style={{ color: '#e05252', marginLeft: 4 }}>*</span>
                  )}
                </label>
                <textarea
                  value={storageReason}
                  onChange={(e) => setStorageReason(e.target.value)}
                  placeholder={
                    storageCondition === '损坏'
                      ? '请填写损坏原因（必填）'
                      : storageCondition === '待报废'
                      ? '请填写待报废原因（必填）'
                      : '请输入入库原因（可选）'
                  }
                  rows="3"
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowStorageModal(false)}>取消</button>
              <button
                className="btn btn-primary"
                onClick={handleStorageConfirm}
                disabled={
                  !storageLocation ||
                  ((storageCondition === '损坏' || storageCondition === '待报废') && !storageReason.trim())
                }
              >
                确认入库
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 报废确认弹窗 */}
      {showRetireModal && (
        <div className="modal-overlay" onClick={() => setShowRetireModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header danger">
              <h2>报废确认</h2>
              <button className="close-btn" onClick={() => setShowRetireModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <p>确定要报废这个资产吗？</p>
              <p style={{ color: '#E05252', fontSize: '13px', marginTop: '8px', marginBottom: '16px' }}>
                报废后资产将无法再分配使用
              </p>
              <div className="form-group">
                <label>报废原因 *</label>
                <textarea
                  value={retireReason}
                  onChange={(e) => setRetireReason(e.target.value)}
                  placeholder="请输入报废原因"
                  rows="3"
                  required
                />
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowRetireModal(false)}>取消</button>
              <button className="btn btn-danger" onClick={handleRetireConfirm} disabled={!retireReason.trim()}>确认报废</button>
            </div>
          </div>
        </div>
      )}

      {/* 添加配件弹窗 */}
      {showPartModal && (
        <div className="modal-overlay" onClick={() => setShowPartModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>添加配件记录</h2>
              <button className="close-btn" onClick={() => setShowPartModal(false)}>&times;</button>
            </div>
            <form onSubmit={handlePartSubmit}>
              <div className="modal-body">
                {/* 操作类型 */}
                <div className="form-group">
                  <label>操作类型 *</label>
                  <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
                    {['新增', '更换'].map(act => (
                      <button
                        key={act}
                        type="button"
                        onClick={() => setPartForm(prev => ({ ...prev, action: act }))}
                        style={{
                          padding: '6px 20px', borderRadius: 6, fontSize: 13, cursor: 'pointer',
                          border: `2px solid ${partForm.action === act ? (act === '新增' ? '#6ee7b7' : '#93c5fd') : 'var(--color-border)'}`,
                          background: partForm.action === act ? (act === '新增' ? '#d1fae5' : '#dbeafe') : '#fff',
                          color: partForm.action === act ? (act === '新增' ? '#065f46' : '#1e40af') : 'var(--color-body)',
                          fontWeight: partForm.action === act ? 700 : 400,
                        }}
                      >
                        {act}
                      </button>
                    ))}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--color-muted)', marginTop: 6 }}>
                    {partForm.action === '新增' ? '新增配件：从库房取出并安装到此设备' : '更换配件：从库房取出新配件替换旧配件'}
                  </div>
                </div>

                {/* 从库房选择配件 */}
                <div className="form-group">
                  <label>从库房选择配件</label>
                  <select
                    value={partForm.warehouse_item_id}
                    onChange={handlePartWarehouseSelect}
                    style={{ width: '100%' }}
                  >
                    <option value="">— 选择库房配件（可选）—</option>
                    {warehouseItems
                      .filter(w => w.available_quantity > 0)
                      .map(w => (
                        <option key={w.id} value={w.id}>
                          {w.name}{w.brand ? ' · ' + w.brand : ''}{w.model ? ' ' + w.model : ''} （可用: {w.available_quantity}）
                        </option>
                      ))
                    }
                  </select>
                  <div style={{ fontSize: 12, color: 'var(--color-muted)', marginTop: 4 }}>
                    选择后自动填充配件名称，并在提交时扣减库房库存
                  </div>
                </div>

                {/* 配件名称（可手动填写） */}
                <div className="form-group">
                  <label>配件名称 *</label>
                  <input
                    type="text"
                    value={partForm.warehouse_item_name}
                    onChange={(e) => setPartForm(prev => ({ ...prev, warehouse_item_name: e.target.value }))}
                    placeholder="例：内存条 DDR4 16GB、固态硬盘 512GB"
                    required
                  />
                </div>

                {/* 数量 */}
                <div className="form-group">
                  <label>数量 *</label>
                  <input
                    type="number"
                    min="1"
                    value={partForm.quantity}
                    onChange={(e) => setPartForm(prev => ({ ...prev, quantity: e.target.value }))}
                    required
                    style={{ width: 100 }}
                  />
                </div>

                {/* 备注 */}
                <div className="form-group">
                  <label>备注</label>
                  <textarea
                    value={partForm.notes}
                    onChange={(e) => setPartForm(prev => ({ ...prev, notes: e.target.value }))}
                    placeholder={partForm.action === '更换' ? '例：原内存条损坏，已报废处理' : '可选备注'}
                    rows="2"
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowPartModal(false)}>取消</button>
                <button type="submit" className="btn btn-primary">确认添加</button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  )
}

export default AssetDetail
