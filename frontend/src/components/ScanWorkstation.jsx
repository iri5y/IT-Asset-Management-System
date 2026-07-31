import { useCallback, useEffect, useRef, useState } from 'react'
import axios from 'axios'
import { AlertCircle, CheckCircle, PackagePlus, Scan, Trash2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''
const CONTROLLED_CATEGORIES = [
  { code: 'PC', name: '台式机' },
  { code: 'NB', name: '笔记本电脑' },
  { code: 'PD', name: '平板电脑' },
]

const errorMessage = (error) => error.response?.data?.detail || error.message || '操作失败，请稍后重试'

const inputStyle = { width: '100%', padding: '8px 10px' }
const labelStyle = { display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 600 }

function TerminalInventorySelect({ inventories, value, onChange, disabled = false }) {
  return (
    <div className="form-group">
      <label style={labelStyle}>终端设备库存 *</label>
      <select style={inputStyle} value={value} disabled={disabled} onChange={event => onChange(event.target.value)}>
        <option value="">请选择终端设备库存</option>
        {inventories.map(item => (
          <option key={item.id} value={item.id}>
            {item.name}（可用 {item.available_quantity}）
          </option>
        ))}
      </select>
    </div>
  )
}

function CategorySelect({ value, onChange, disabled = false }) {
  return (
    <div className="form-group">
      <label style={labelStyle}>固定资产品类 *</label>
      <select style={inputStyle} value={value} disabled={disabled} onChange={event => onChange(event.target.value)}>
        {CONTROLLED_CATEGORIES.map(category => <option key={category.code} value={category.code}>{category.name}</option>)}
      </select>
    </div>
  )
}

function SingleInbound({ inventories, onSuccess }) {
  const [form, setForm] = useState({
    source: 'SCAN', asset_category_code: 'NB', terminal_inventory_id: '',
    fixed_asset_number: '', serial_number: '', brand: '', model: '', notes: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState(null)
  const serialInput = useRef(null)

  const setField = (field, value) => setForm(previous => ({ ...previous, [field]: value }))

  const submit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    setResult(null)
    try {
      const response = await axios.post(`${API_URL}/fixed-assets/inbound`, {
        ...form,
        terminal_inventory_id: Number(form.terminal_inventory_id),
        brand: form.brand.trim() || undefined,
        model: form.model.trim() || undefined,
        notes: form.notes.trim() || undefined,
      })
      setResult({ success: true, message: `资产 ${response.data.asset.fixed_asset_number} 已受控入库，当前状态为闲置。` })
      setForm(previous => ({ ...previous, fixed_asset_number: '', serial_number: '', notes: '' }))
      onSuccess()
      serialInput.current?.focus()
    } catch (error) {
      setResult({ success: false, message: errorMessage(error) })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={submit} style={{ maxWidth: 780 }}>
      <div className="form-row">
        <CategorySelect value={form.asset_category_code} onChange={value => setField('asset_category_code', value)} disabled={submitting} />
        <TerminalInventorySelect inventories={inventories} value={form.terminal_inventory_id} onChange={value => setField('terminal_inventory_id', value)} disabled={submitting} />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label style={labelStyle}>入库来源 *</label>
          <select style={inputStyle} value={form.source} disabled={submitting} onChange={event => setField('source', event.target.value)}>
            <option value="SCAN">扫码入库</option>
            <option value="MANUAL">手动录入</option>
          </select>
        </div>
        <div className="form-group">
          <label style={labelStyle}>资产编号 *</label>
          <input style={inputStyle} required value={form.fixed_asset_number} disabled={submitting} onChange={event => setField('fixed_asset_number', event.target.value)} placeholder="例如：ZS-NB26-000001" />
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label style={labelStyle}>序列号（SN）*</label>
          <input ref={serialInput} style={inputStyle} required value={form.serial_number} disabled={submitting} onChange={event => setField('serial_number', event.target.value)} placeholder="扫描或手动输入设备 SN" autoComplete="off" />
        </div>
        <div className="form-group">
          <label style={labelStyle}>品牌（可选）</label>
          <input style={inputStyle} value={form.brand} disabled={submitting} onChange={event => setField('brand', event.target.value)} />
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label style={labelStyle}>型号（可选）</label>
          <input style={inputStyle} value={form.model} disabled={submitting} onChange={event => setField('model', event.target.value)} />
        </div>
        <div className="form-group">
          <label style={labelStyle}>备注（可选）</label>
          <input style={inputStyle} value={form.notes} disabled={submitting} onChange={event => setField('notes', event.target.value)} />
        </div>
      </div>
      <button className="btn btn-primary" type="submit" disabled={submitting || !form.terminal_inventory_id}>
        <Scan size={15} /> {submitting ? '受控入库中…' : '提交单件受控入库'}
      </button>
      {result && <ResultNotice result={result} />}
    </form>
  )
}

function ResultNotice({ result }) {
  const Icon = result.success ? CheckCircle : AlertCircle
  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 14, color: result.success ? 'var(--color-success)' : 'var(--color-danger)', fontSize: 13 }}>
      <Icon size={16} /><span>{result.message}</span>
    </div>
  )
}

function nextAssetNumber(startNumber, index) {
  const match = startNumber.trim().match(/^(.*?)(\d+)$/)
  if (!match) return index === 0 ? startNumber.trim() : `${startNumber.trim()}-${index + 1}`
  return `${match[1]}${String(Number(match[2]) + index).padStart(match[2].length, '0')}`
}

function BatchInbound({ inventories, onSuccess }) {
  const [category, setCategory] = useState('NB')
  const [source, setSource] = useState('SCAN')
  const [terminalInventoryId, setTerminalInventoryId] = useState('')
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const [startNumber, setStartNumber] = useState('')
  const [serialInput, setSerialInput] = useState('')
  const [items, setItems] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [results, setResults] = useState([])
  const scannerRef = useRef(null)

  const addSerial = useCallback(() => {
    const serialNumber = serialInput.trim()
    if (!serialNumber || !startNumber.trim()) return
    if (items.some(item => item.serial_number.toUpperCase() === serialNumber.toUpperCase())) return
    setItems(previous => [...previous, {
      serial_number: serialNumber,
      fixed_asset_number: nextAssetNumber(startNumber, previous.length),
    }])
    setSerialInput('')
    scannerRef.current?.focus()
  }, [items, serialInput, startNumber])

  const submit = async () => {
    if (!terminalInventoryId || items.length === 0) return
    setSubmitting(true)
    try {
      const response = await axios.post(`${API_URL}/fixed-assets/inbound/batch`, {
        items: items.map(item => ({
          source,
          asset_category_code: category,
          terminal_inventory_id: Number(terminalInventoryId),
          fixed_asset_number: item.fixed_asset_number,
          serial_number: item.serial_number,
          brand: brand.trim() || undefined,
          model: model.trim() || undefined,
        })),
      })
      const batchResults = response.data.results || []
      setResults(batchResults)
      const failedItems = batchResults
        .filter(item => !item.success)
        .map(item => ({ serial_number: item.serial_number, fixed_asset_number: item.fixed_asset_number }))
      setItems(failedItems)
      if (batchResults.some(item => item.success)) onSuccess()
    } catch (error) {
      setResults(items.map((item, index) => ({
        index,
        ...item,
        success: false,
        message: errorMessage(error),
      })))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div style={{ maxWidth: 860 }}>
      <div className="form-row">
        <CategorySelect value={category} onChange={setCategory} disabled={submitting} />
        <TerminalInventorySelect inventories={inventories} value={terminalInventoryId} onChange={setTerminalInventoryId} disabled={submitting} />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label style={labelStyle}>逐项来源 *</label>
          <select style={inputStyle} value={source} disabled={submitting} onChange={event => setSource(event.target.value)}>
            <option value="SCAN">扫码入库</option>
            <option value="MANUAL">手动录入</option>
          </select>
        </div>
        <div className="form-group">
          <label style={labelStyle}>起始资产编号 *</label>
          <input style={inputStyle} value={startNumber} disabled={submitting} onChange={event => setStartNumber(event.target.value)} placeholder="例如：ZS-NB26-000001" />
        </div>
      </div>
      <div className="form-row">
        <div className="form-group"><label style={labelStyle}>品牌（可选）</label><input style={inputStyle} value={brand} disabled={submitting} onChange={event => setBrand(event.target.value)} /></div>
        <div className="form-group"><label style={labelStyle}>型号（可选）</label><input style={inputStyle} value={model} disabled={submitting} onChange={event => setModel(event.target.value)} /></div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        <input ref={scannerRef} style={{ ...inputStyle, flex: 1 }} value={serialInput} disabled={submitting} onChange={event => setSerialInput(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') { event.preventDefault(); addSerial() } }} placeholder="扫描 SN 或手动输入后按 Enter" autoComplete="off" />
        <button className="btn btn-secondary" type="button" disabled={submitting || !serialInput.trim() || !startNumber.trim()} onClick={addSerial}>添加</button>
      </div>
      <p style={{ margin: '-6px 0 12px', color: 'var(--color-muted)', fontSize: 12 }}>每个序列号将独立提交；失败项会保留在下方列表，修正后可再次提交。</p>
      <BatchItems items={items} setItems={setItems} disabled={submitting} />
      <button className="btn btn-primary" type="button" disabled={submitting || !terminalInventoryId || items.length === 0} onClick={submit}>
        <PackagePlus size={15} /> {submitting ? '逐项受控入库中…' : `提交 ${items.length} 项受控入库`}
      </button>
      {results.length > 0 && <BatchResults results={results} />}
    </div>
  )
}

function BatchItems({ items, setItems, disabled }) {
  if (items.length === 0) return <div style={{ padding: 18, marginBottom: 14, background: 'var(--color-bg)', color: 'var(--color-muted)', fontSize: 13 }}>尚未添加序列号。</div>
  return (
    <div style={{ overflowX: 'auto', marginBottom: 14 }}>
      <table className="scan-history-table" style={{ width: '100%' }}>
        <thead><tr><th>#</th><th>资产编号</th><th>序列号</th><th>操作</th></tr></thead>
        <tbody>{items.map((item, index) => (
          <tr key={`${item.fixed_asset_number}-${item.serial_number}`}>
            <td>{index + 1}</td>
            <td><input style={inputStyle} value={item.fixed_asset_number} disabled={disabled} onChange={event => setItems(previous => previous.map((row, rowIndex) => rowIndex === index ? { ...row, fixed_asset_number: event.target.value } : row))} /></td>
            <td><input style={inputStyle} value={item.serial_number} disabled={disabled} onChange={event => setItems(previous => previous.map((row, rowIndex) => rowIndex === index ? { ...row, serial_number: event.target.value } : row))} /></td>
            <td><button className="btn btn-danger btn-sm" type="button" disabled={disabled} onClick={() => setItems(previous => previous.filter((_, rowIndex) => rowIndex !== index))}><Trash2 size={14} /> 删除</button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

function BatchResults({ results }) {
  const successCount = results.filter(item => item.success).length
  return (
    <div style={{ marginTop: 16 }}>
      <ResultNotice result={{ success: successCount === results.length, message: `批量处理完成：成功 ${successCount} 项，失败 ${results.length - successCount} 项。` }} />
      <table className="scan-history-table" style={{ width: '100%', marginTop: 10 }}>
        <thead><tr><th>资产编号</th><th>序列号</th><th>结果</th></tr></thead>
        <tbody>{results.map((item, index) => <tr key={`${item.serial_number}-${index}`}><td>{item.fixed_asset_number}</td><td>{item.serial_number}</td><td style={{ color: item.success ? 'var(--color-success)' : 'var(--color-danger)' }}>{item.success ? '成功：已创建闲置固定资产卡' : `失败：${item.message}`}</td></tr>)}</tbody>
      </table>
    </div>
  )
}

function ScanWorkstation() {
  const { isReadOnly } = useAuth()
  const [mode, setMode] = useState('single')
  const [inventories, setInventories] = useState([])
  const [loadError, setLoadError] = useState('')
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let active = true
    axios.get(`${API_URL}/warehouse/materials`)
      .then(response => {
        if (!active) return
        const terminalInventories = (response.data || []).filter(item => item.primary_category_code === 'TERMINAL_EQUIPMENT')
        setInventories(terminalInventories)
        setLoadError(terminalInventories.length ? '' : '没有可用的“终端设备库存”记录，请先由仓储管理员建立受控终端库存。')
      })
      .catch(error => active && setLoadError(`无法加载终端设备库存：${errorMessage(error)}`))
    return () => { active = false }
  }, [refreshKey])

  if (isReadOnly) {
    return <div className="scan-workstation"><h2><Scan size={20} /> 扫码工作台</h2><div style={{ padding: 24, color: 'var(--color-muted)' }}>只读账号可查看资产信息，但无权限执行固定资产入库。</div></div>
  }

  return (
    <div className="scan-workstation">
      <div className="scan-header">
        <div><h2><Scan size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />固定资产受控入库</h2><p style={{ color: 'var(--color-muted)', fontSize: 13 }}>仅支持台式机、笔记本电脑和平板电脑；每台设备必须有唯一资产编号和序列号。</p></div>
        <div style={{ display: 'flex', gap: 8 }}><button className={`btn btn-sm ${mode === 'single' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('single')}>单件入库</button><button className={`btn btn-sm ${mode === 'batch' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setMode('batch')}>批量入库</button></div>
      </div>
      {loadError && <ResultNotice result={{ success: false, message: loadError }} />}
      <div style={{ marginTop: 18, padding: 20, background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)' }}>
        {mode === 'single' ? <SingleInbound inventories={inventories} onSuccess={() => setRefreshKey(key => key + 1)} /> : <BatchInbound inventories={inventories} onSuccess={() => setRefreshKey(key => key + 1)} />}
      </div>
    </div>
  )
}

export default ScanWorkstation
