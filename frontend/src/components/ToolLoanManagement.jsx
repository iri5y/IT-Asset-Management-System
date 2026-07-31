import { useEffect, useState } from 'react'
import axios from 'axios'
import { Wrench, RotateCcw } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''
const nowInputValue = () => new Date().toISOString().slice(0, 16)

function ToolLoanManagement() {
  const { isReadOnly } = useAuth()
  const [loans, setLoans] = useState([])
  const [materials, setMaterials] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showLoanForm, setShowLoanForm] = useState(false)
  const [returningLoan, setReturningLoan] = useState(null)
  const [selectedLoan, setSelectedLoan] = useState(null)

  const loadData = async () => {
    try {
      setLoading(true)
      const [loanResponse, materialResponse] = await Promise.all([
        axios.get(`${API_URL}/tool-loans`),
        axios.get(`${API_URL}/warehouse/materials`),
      ])
      setLoans(loanResponse.data)
      setMaterials(materialResponse.data.filter(item => item.primary_category_code === 'IT_TOOLS_LOAN_ITEMS'))
      setError('')
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '获取工具借用记录失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const handleLoan = async (payload) => {
    try {
      await axios.post(`${API_URL}/tool-loans`, payload)
      setShowLoanForm(false)
      await loadData()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '工具借出失败')
    }
  }


  const handleReturn = async (payload) => {
    try {
      await axios.post(`${API_URL}/tool-loans/${returningLoan.id}/returns`, payload)
      setReturningLoan(null)
      await loadData()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '工具归还失败')
    }
  }

  return (
    <div className="warehouse-container">
      <div className="warehouse-header">
        <div>
          <h2>IT工具借还管理</h2>
          <p>借用中工具会显示未归还数量；贵重工具可记录工具编号或二维码。</p>
        </div>
        {!isReadOnly && <button className="btn btn-primary" onClick={() => setShowLoanForm(true)}>+ 借出工具</button>}
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      {loading ? <div className="loading">加载中...</div> : (
        <div className="warehouse-by-location">
          {loans.length === 0 ? <div className="empty-state"><h3>暂无工具借用记录</h3></div> : loans.map(loan => (
            <div className="warehouse-grid-card" key={loan.id}>
              <div className="grid-card-header">
                <button className="grid-card-name" onClick={() => setSelectedLoan(loan)}>{loan.material_name}</button>
                <span className={`status-badge ${loan.status === 'BORROWED' ? 'status-使用中' : 'status-闲置'}`}>
                  {loan.status === 'BORROWED' ? '借用中' : '已归还'}
                </span>
              </div>
              <div className="grid-card-info">借用人：{loan.borrower_ref}</div>
              <div className="grid-card-quantity">
                <span>借出：<strong className="font-data">{loan.quantity}</strong></span>
                <span>未归还：<strong className="font-data">{loan.unreturned_quantity}</strong></span>
              </div>
              <div className="grid-card-info">预计归还：{formatDate(loan.expected_return_at)}</div>
              {loan.tool_identifier && <div className="grid-card-info">工具编号/二维码：{loan.tool_identifier}</div>}
              {!isReadOnly && loan.status === 'BORROWED' && (
                <div className="record-actions"><button className="btn btn-secondary" onClick={() => setReturningLoan(loan)}><RotateCcw size={16} /> 归还</button></div>
              )}
            </div>
          ))}
        </div>
      )}
      {showLoanForm && <ToolLoanForm materials={materials} onClose={() => setShowLoanForm(false)} onSubmit={handleLoan} />}
      {returningLoan && <ToolReturnForm loan={returningLoan} onClose={() => setReturningLoan(null)} onSubmit={handleReturn} />}
      {selectedLoan && <ToolLoanDetail loan={selectedLoan} onClose={() => setSelectedLoan(null)} />}
    </div>
  )
}

function ToolLoanForm({ materials, onClose, onSubmit }) {
  const [form, setForm] = useState({ warehouse_asset_id: '', borrower_ref: '', quantity: 1, borrowed_at: nowInputValue(), expected_return_at: '', tool_identifier: '' })
  const submit = event => {
    event.preventDefault()
    onSubmit({ ...form, warehouse_asset_id: Number(form.warehouse_asset_id), quantity: Number(form.quantity), borrowed_at: new Date(form.borrowed_at).toISOString(), expected_return_at: new Date(form.expected_return_at).toISOString(), tool_identifier: form.tool_identifier || null })
  }
  return <div className="modal-overlay" onClick={onClose}><div className="modal-content" onClick={event => event.stopPropagation()}>
    <div className="modal-header"><h2><Wrench size={20} /> 借出IT工具</h2><button className="close-btn" onClick={onClose}>&times;</button></div>
    <form onSubmit={submit}><div className="modal-body">
      <div className="form-group"><label>IT工具物料 *</label><select required value={form.warehouse_asset_id} onChange={event => setForm({ ...form, warehouse_asset_id: event.target.value })}><option value="">请选择工具</option>{materials.map(item => <option key={item.id} value={item.id}>{item.name}（可用 {item.available_quantity}）</option>)}</select></div>
      <div className="form-row"><div className="form-group"><label>借用人 *</label><input required value={form.borrower_ref} onChange={event => setForm({ ...form, borrower_ref: event.target.value })} /></div><div className="form-group"><label>借用数量 *</label><input type="number" min="1" required value={form.quantity} onChange={event => setForm({ ...form, quantity: event.target.value })} /></div></div>
      <div className="form-row"><div className="form-group"><label>借出时间 *</label><input type="datetime-local" required value={form.borrowed_at} onChange={event => setForm({ ...form, borrowed_at: event.target.value })} /></div><div className="form-group"><label>预计归还时间 *</label><input type="datetime-local" required value={form.expected_return_at} onChange={event => setForm({ ...form, expected_return_at: event.target.value })} /></div></div>
      <div className="form-group"><label>工具编号/二维码（贵重工具可选）</label><input value={form.tool_identifier} onChange={event => setForm({ ...form, tool_identifier: event.target.value })} /></div>
    </div><div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={onClose}>取消</button><button className="btn btn-primary" type="submit">确认借出</button></div></form>
  </div></div>
}

function ToolReturnForm({ loan, onClose, onSubmit }) {
  const [quantity, setQuantity] = useState(loan.unreturned_quantity)
  const [returnedAt, setReturnedAt] = useState(nowInputValue())
  const submit = event => { event.preventDefault(); onSubmit({ quantity: Number(quantity), returned_at: new Date(returnedAt).toISOString() }) }
  return <div className="modal-overlay" onClick={onClose}><div className="modal-content" onClick={event => event.stopPropagation()}>
    <div className="modal-header"><h2>归还工具：{loan.material_name}</h2><button className="close-btn" onClick={onClose}>&times;</button></div>
    <form onSubmit={submit}><div className="modal-body"><p>当前未归还数量：<strong>{loan.unreturned_quantity}</strong></p><div className="form-row"><div className="form-group"><label>本次归还数量 *</label><input type="number" min="1" max={loan.unreturned_quantity} required value={quantity} onChange={event => setQuantity(event.target.value)} /></div><div className="form-group"><label>归还时间 *</label><input type="datetime-local" required value={returnedAt} onChange={event => setReturnedAt(event.target.value)} /></div></div></div><div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={onClose}>取消</button><button className="btn btn-primary" type="submit">确认归还</button></div></form>
  </div></div>
}

function ToolLoanDetail({ loan, onClose }) {
  return <div className="modal-overlay" onClick={onClose}><div className="modal-content" onClick={event => event.stopPropagation()}><div className="modal-header"><h2>工具借用详情</h2><button className="close-btn" onClick={onClose}>&times;</button></div><div className="modal-body"><p><strong>物料：</strong>{loan.material_name}</p><p><strong>借用状态：</strong>{loan.status === 'BORROWED' ? '借用中' : '已归还'}</p><p><strong>未归还数量：</strong>{loan.unreturned_quantity}</p><p><strong>借用人：</strong>{loan.borrower_ref}</p><p><strong>借出时间：</strong>{formatDate(loan.borrowed_at)}</p><p><strong>预计归还：</strong>{formatDate(loan.expected_return_at)}</p>{loan.tool_identifier && <p><strong>工具编号/二维码：</strong>{loan.tool_identifier}</p>}</div></div></div>
}

function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : '-' }

export default ToolLoanManagement
