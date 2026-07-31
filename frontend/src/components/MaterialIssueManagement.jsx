import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { ClipboardList } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''
const nowInputValue = () => new Date().toISOString().slice(0, 16)

const ISSUE_TYPES = {
  standard: { label: '低值物料发放与归还', endpoint: '/material-issues' },
  repair: { label: '维修备件发放', endpoint: '/repair-parts/issues', category: 'STORAGE_REPAIR_PARTS' },
  network: { label: '网络与机房耗材发放', endpoint: '/network-consumables/issues', category: 'NETWORK_SERVER_ROOM_CONSUMABLES' },
  office: { label: '办公与通用耗材发放', endpoint: '/office-consumables/issues', category: 'OFFICE_GENERAL_CONSUMABLES' },
}

const issuePolicyLabel = policy => policy === 'RETURNABLE' ? '待归还' : '一次性消耗品'

function MaterialIssueManagement() {
  const { isReadOnly } = useAuth()
  const [issueType, setIssueType] = useState('standard')
  const [materials, setMaterials] = useState([])
  const [departments, setDepartments] = useState([])
  const [assets, setAssets] = useState([])
  const [normalIssues, setNormalIssues] = useState([])
  const [returnDrafts, setReturnDrafts] = useState({})
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [returningId, setReturningId] = useState(null)
  const [form, setForm] = useState(emptyForm())

  const availableMaterials = useMemo(() => issueType === 'standard'
    ? materials
    : materials.filter(item => item.primary_category_code === ISSUE_TYPES[issueType].category), [materials, issueType])
  const selectedMaterial = useMemo(() => materials.find(item => item.id === Number(form.warehouse_asset_id)), [materials, form.warehouse_asset_id])

  const refreshMaterials = async () => {
    const response = await axios.get(`${API_URL}/warehouse/materials`)
    setMaterials(response.data)
  }

  useEffect(() => {
    Promise.all([
      axios.get(`${API_URL}/warehouse/materials`),
      axios.get(`${API_URL}/departments/flat`),
      axios.get(`${API_URL}/assets/`, { params: { limit: 10000 } }),
    ]).then(([materialResponse, departmentResponse, assetResponse]) => {
      setMaterials(materialResponse.data)
      setDepartments(departmentResponse.data)
      setAssets(assetResponse.data)
    }).catch(requestError => setError(requestError.response?.data?.detail || '加载物料数据失败'))
  }, [])

  const switchType = nextType => { setIssueType(nextType); setForm(emptyForm()); setMessage(''); setError('') }
  const update = (name, value) => setForm(current => ({ ...current, [name]: value }))
  const updateReturnDraft = (issueId, name, value) => setReturnDrafts(current => ({
    ...current,
    [issueId]: { quantity: current[issueId]?.quantity ?? '', returned_at: current[issueId]?.returned_at ?? nowInputValue(), [name]: value },
  }))

  const submit = async event => {
    event.preventDefault()
    setMessage('')
    setError('')
    if (issueType === 'network' && hasNetworkPurpose(form) && !hasValidNetworkPurpose(form)) {
      setError('填写网络用途时，必须提供有效部门、项目、机房或工单关联')
      return
    }
    const payload = issueType === 'standard' ? buildStandardPayload(form) : buildPayload(issueType, form)
    try {
      setSubmitting(true)
      const response = await axios.post(`${API_URL}${ISSUE_TYPES[issueType].endpoint}`, payload)
      setMessage(`发放成功，审计编号：${response.data.audit_log_id}`)
      if (issueType === 'standard') {
        setNormalIssues(current => [{ ...response.data.material_issue, material_name: response.data.inventory.name }, ...current])
      }
      setForm(emptyForm())
      await refreshMaterials()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '物料发放失败')
    } finally {
      setSubmitting(false)
    }
  }

  const submitReturn = async issue => {
    const draft = returnDrafts[issue.id] || { quantity: issue.unreturned_quantity, returned_at: nowInputValue() }
    const quantity = Number(draft.quantity || issue.unreturned_quantity)
    if (!Number.isInteger(quantity) || quantity <= 0) {
      setError('归还数量必须为大于零的整数')
      return
    }
    setMessage('')
    setError('')
    try {
      setReturningId(issue.id)
      const response = await axios.post(`${API_URL}/material-issues/${issue.id}/returns`, {
        quantity,
        returned_at: new Date(draft.returned_at).toISOString(),
      })
      setNormalIssues(current => current.map(item => item.id === issue.id ? { ...item, ...response.data.material_issue } : item))
      setReturnDrafts(current => ({ ...current, [issue.id]: { quantity: '', returned_at: nowInputValue() } }))
      setMessage(`归还成功，审计编号：${response.data.audit_log_id}`)
      await refreshMaterials()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '低值物料归还失败')
    } finally {
      setReturningId(null)
    }
  }

  return <div className="warehouse-container">
    <div className="warehouse-header"><div><h2><ClipboardList size={22} /> 物料发放管理</h2><p>低值物料按“待归还”或“一次性消耗品”策略留痕；维修、网络和办公耗材保留原有专用流程。</p></div></div>
    <div className="nav-tabs">{Object.entries(ISSUE_TYPES).map(([key, item]) => <button key={key} className={`nav-tab ${issueType === key ? 'active' : ''}`} onClick={() => switchType(key)}>{item.label}</button>)}</div>
    {message && <div className="alert alert-success">{message}</div>}
    {error && <div className="alert alert-error">{error}</div>}
    {issueType === 'standard' ? <>
      {isReadOnly ? <ReadOnlyMaterialList materials={availableMaterials} type={issueType} /> : <form className="modal-content" style={{ maxWidth: '900px', margin: '24px 0' }} onSubmit={submit}>
        <div className="modal-body">
          <div className="form-row"><div className="form-group"><label>低值物料 *</label><select value={form.warehouse_asset_id} required onChange={event => update('warehouse_asset_id', event.target.value)}><option value="">请选择物料</option>{availableMaterials.map(item => <option key={item.id} value={item.id}>{item.name}（可用 {item.available_quantity}，{issuePolicyLabel(item.issue_policy)}）</option>)}</select></div><div className="form-group"><label>发放数量 *</label><input type="number" min="1" step="1" value={form.quantity} required onChange={event => update('quantity', event.target.value)} /></div></div>
          {selectedMaterial && <div className="alert alert-info">本次策略快照：<strong>{issuePolicyLabel(selectedMaterial.issue_policy)}</strong>{selectedMaterial.issue_policy === 'CONSUMABLE' ? '，发放完成后不可归还。' : '，可在下方按剩余数量部分或全量归还。'}</div>}
          <div className="form-group"><label>发放日期和时间 *</label><input type="datetime-local" value={form.issued_at} required onChange={event => update('issued_at', event.target.value)} /></div>
          <div className="form-row"><div className="form-group"><label>领用人（选填）</label><input value={form.recipient_name} onChange={event => update('recipient_name', event.target.value)} /></div><div className="form-group"><label>工号（选填）</label><input value={form.recipient_employee_id} onChange={event => update('recipient_employee_id', event.target.value)} /></div></div>
          <div className="form-row"><div className="form-group"><label>部门（选填）</label><input value={form.recipient_department} onChange={event => update('recipient_department', event.target.value)} /></div><div className="form-group"><label>用途（选填）</label><input value={form.purpose} onChange={event => update('purpose', event.target.value)} /></div></div>
        </div>
        <div className="modal-footer"><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? '提交中...' : '确认发放'}</button></div>
      </form>}
      <MaterialIssueHistory issues={normalIssues} returnDrafts={returnDrafts} updateReturnDraft={updateReturnDraft} submitReturn={submitReturn} returningId={returningId} isReadOnly={isReadOnly} />
    </> : isReadOnly ? <ReadOnlyMaterialList materials={availableMaterials} type={issueType} /> : <form className="modal-content" style={{ maxWidth: '900px', margin: '24px 0' }} onSubmit={submit}>
      <div className="modal-body">
        <div className="form-row"><div className="form-group"><label>{ISSUE_TYPES[issueType].label}物料 *</label><select value={form.warehouse_asset_id} required onChange={event => update('warehouse_asset_id', event.target.value)}><option value="">请选择物料</option>{availableMaterials.map(item => <option key={item.id} value={item.id}>{item.name}（可用 {item.available_quantity}）</option>)}</select></div><div className="form-group"><label>发放数量 *</label><input type="number" min="1" value={form.quantity} required onChange={event => update('quantity', event.target.value)} /></div></div>
        <div className="form-group"><label>发放日期和时间 *</label><input type="datetime-local" value={form.issued_at} required onChange={event => update('issued_at', event.target.value)} /></div>
        {issueType === 'repair' && <RepairAssociation form={form} update={update} assets={assets} />}
        {issueType === 'network' && <NetworkPurpose form={form} update={update} departments={departments} />}
        {issueType === 'office' && <div className="alert alert-info"><strong>领用策略：一次性消耗品。</strong>办公与通用耗材发放后不可归还。</div>}
      </div>
      <div className="modal-footer"><button className="btn btn-primary" type="submit" disabled={submitting}>{submitting ? '提交中...' : '确认发放'}</button></div>
    </form>}
  </div>
}

function MaterialIssueHistory({ issues, returnDrafts, updateReturnDraft, submitReturn, returningId, isReadOnly }) {
  return <div className="warehouse-by-location" style={{ marginTop: '24px' }}><h3>本次会话低值发放记录</h3>{issues.length === 0 ? <div className="empty-state"><h3>暂无低值发放记录</h3><p>成功发放后会在此显示策略快照和未归还余额。</p></div> : issues.map(issue => {
    const canReturn = issue.record_type === 'RETURNABLE' && !issue.consumed_completed && issue.unreturned_quantity > 0
    const draft = returnDrafts[issue.id] || { quantity: issue.unreturned_quantity, returned_at: nowInputValue() }
    return <div key={issue.id} className="warehouse-grid-card"><div className="grid-card-header"><span className="grid-card-name">{issue.material_name || `物料 #${issue.warehouse_asset_id}`}</span><span className="status-badge">{issuePolicyLabel(issue.issue_policy)}</span></div><div className="grid-card-quantity"><span>发放：<strong>{issue.quantity}</strong></span><span>未归还：<strong>{issue.unreturned_quantity}</strong></span></div><div>领用人：{issue.recipient_name || '未填写'}　工号：{issue.recipient_employee_id || '未填写'}　部门：{issue.recipient_department || '未填写'}</div><div>用途：{issue.purpose || '未填写'}</div>{issue.consumed_completed ? <div className="alert alert-info">一次性消耗完成，禁止归还。</div> : canReturn ? <div className="form-row" style={{ marginTop: '12px' }}><div className="form-group"><label>归还数量</label><input type="number" min="1" max={issue.unreturned_quantity} value={draft.quantity} onChange={event => updateReturnDraft(issue.id, 'quantity', event.target.value)} disabled={isReadOnly || returningId === issue.id} /></div><div className="form-group"><label>归还日期和时间</label><input type="datetime-local" value={draft.returned_at} onChange={event => updateReturnDraft(issue.id, 'returned_at', event.target.value)} disabled={isReadOnly || returningId === issue.id} /></div>{!isReadOnly && <div className="form-group" style={{ alignSelf: 'end' }}><button type="button" className="btn btn-primary" disabled={returningId === issue.id} onClick={() => submitReturn(issue)}>{returningId === issue.id ? '归还中...' : '确认归还'}</button></div>}</div> : <div className="alert alert-success">已全部归还。</div>}</div>
  })}</div>
}

function buildStandardPayload(form) {
  return {
    warehouse_asset_id: Number(form.warehouse_asset_id),
    quantity: Number(form.quantity),
    issued_at: new Date(form.issued_at).toISOString(),
    recipient_name: form.recipient_name || null,
    recipient_employee_id: form.recipient_employee_id || null,
    recipient_department: form.recipient_department || null,
    purpose: form.purpose || null,
  }
}

function RepairAssociation({ form, update, assets }) {
  return <><div className="form-row"><div className="form-group"><label>维修对象资产（与维修单至少填写一项）</label><select value={form.target_asset_id} onChange={event => update('target_asset_id', event.target.value)}><option value="">不关联固定资产</option>{assets.map(asset => <option key={asset.id} value={asset.id}>{asset.asset_tag} / {asset.category} / {asset.status}</option>)}</select></div><div className="form-group"><label>维修单号（与维修对象至少填写一项）</label><input value={form.repair_order_ref} onChange={event => update('repair_order_ref', event.target.value)} /></div></div><div className="form-group"><label>硬盘序列号（硬盘备件可选）</label><input value={form.disk_serial_number} onChange={event => update('disk_serial_number', event.target.value)} /></div></>
}

function NetworkPurpose({ form, update, departments }) {
  return <><div className="alert alert-info">网络用途可不填写；如填写任一用途，系统会校验至少一个有效关联。</div><div className="form-row"><div className="form-group"><label>部门</label><select value={form.department_id} onChange={event => update('department_id', event.target.value)}><option value="">不关联部门</option>{departments.map(department => <option key={department.id} value={department.id}>{department.display || department.name}</option>)}</select></div><div className="form-group"><label>项目</label><input value={form.project_ref} onChange={event => update('project_ref', event.target.value)} /></div></div><div className="form-row"><div className="form-group"><label>机房</label><input value={form.server_room_ref} onChange={event => update('server_room_ref', event.target.value)} /></div><div className="form-group"><label>工单</label><input value={form.work_order_ref} onChange={event => update('work_order_ref', event.target.value)} /></div></div></>
}

function ReadOnlyMaterialList({ materials, type }) {
  const strategy = type === 'office' ? '一次性消耗品' : '仅可查看库存，写入操作需写权限'
  return <div className="warehouse-by-location"><div className="alert alert-info">只读账号：{strategy}</div>{materials.length === 0 ? <div className="empty-state"><h3>暂无可查看物料</h3></div> : materials.map(item => <div key={item.id} className="warehouse-grid-card"><div className="grid-card-header"><span className="grid-card-name">{item.name}</span>{item.low_stock && <span className="status-badge status-维修中">低库存预警</span>}</div><div className="grid-card-quantity"><span>可用：<strong>{item.available_quantity}</strong></span><span>已分配：{item.allocated_quantity}</span></div></div>)}</div>
}

function emptyForm() {
  return {
    warehouse_asset_id: '',
    quantity: 1,
    issued_at: nowInputValue(),
    recipient_name: '',
    recipient_employee_id: '',
    recipient_department: '',
    purpose: '',
    target_asset_id: '',
    repair_order_ref: '',
    disk_serial_number: '',
    department_id: '',
    project_ref: '',
    server_room_ref: '',
    work_order_ref: '',
  }
}
function hasNetworkPurpose(form) { return Boolean(form.department_id || form.project_ref || form.server_room_ref || form.work_order_ref) }
function hasValidNetworkPurpose(form) { return Boolean(Number(form.department_id) > 0 || form.project_ref.trim() || form.server_room_ref.trim() || form.work_order_ref.trim()) }
function buildPayload(type, form) {
  const base = { warehouse_asset_id: Number(form.warehouse_asset_id), quantity: Number(form.quantity), issued_at: new Date(form.issued_at).toISOString() }
  if (type === 'repair') return { ...base, target_asset_id: form.target_asset_id ? Number(form.target_asset_id) : null, repair_order_ref: form.repair_order_ref || null, disk_serial_number: form.disk_serial_number || null }
  if (type === 'network') return { ...base, department_id: form.department_id ? Number(form.department_id) : null, project_ref: form.project_ref || null, server_room_ref: form.server_room_ref || null, work_order_ref: form.work_order_ref || null }
  return base
}

export default MaterialIssueManagement
