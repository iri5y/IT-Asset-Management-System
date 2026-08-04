import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'
import { Scan, CheckCircle, AlertCircle, Clock, Trash2, Info, PackagePlus, ArrowLeft, X } from 'lucide-react'
import AssetModal from './AssetModal'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''
const SCAN_BUFFER_MS = 80

// ========== 批量入库子组件 ==========
function BulkInbound({ onBack }) {
  // 步骤：'setup'（填写基本信息）| 'scan'（扫码阶段）| 'confirm'（确认提交）
  const [step, setStep] = useState('setup')

  // 步骤1：基本信息
  const [category, setCategory] = useState('笔记本电脑')
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const [poNumber, setPoNumber] = useState('')
  const [startTag, setStartTag] = useState('')   // 起始资产编号（系统建议，可修改）
  const [loadingTag, setLoadingTag] = useState(false)
  const [brands, setBrands] = useState([])

  // 步骤2：扫码
  const [scannedList, setScannedList] = useState([])  // [{sn, asset_tag, duplicate}]
  const [scanInput, setScanInput] = useState('')
  const [scanError, setScanError] = useState('')
  const scanInputRef = useRef(null)
  const bufferRef = useRef('')
  const timerRef = useRef(null)

  // 步骤3：提交
  const [submitting, setSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState(null)

  useEffect(() => {
    axios.get(`${API_URL}/brands/`).then(res => setBrands(res.data)).catch(() => {})
  }, [])

  // 品类变化时自动获取下一个建议编号
  useEffect(() => {
    if (!category) return
    fetchNextTag(category)
  }, [category])

  const fetchNextTag = async (cat) => {
    setLoadingTag(true)
    try {
      const res = await axios.get(`${API_URL}/assets/next-tag/${encodeURIComponent(cat)}`)
      setStartTag(res.data.suggested_tag)
    } catch {
      setStartTag('')
    } finally {
      setLoadingTag(false)
    }
  }

  // 从 startTag 解析前缀和起始序号，生成第 n 个编号
  const generateTag = useCallback((index) => {
    const m = startTag.match(/^(ZS-[A-Za-z0-9]{4}-)(\d{6})$/)
    if (!m) return `${startTag}_${index + 1}`
    const num = parseInt(m[2]) + index
    return `${m[1]}${String(num).padStart(6, '0')}`
  }, [startTag])

  // 验证 startTag 格式
  const isValidStartTag = /^ZS-[A-Za-z0-9]{4}-\d{6}$/.test(startTag)

  const handleSetupNext = () => {
    if (!poNumber.trim()) { alert('请填写PO号'); return }
    if (!isValidStartTag) { alert('起始资产编号格式不正确，应为 ZS-XXXX-NNNNNN'); return }
    setScannedList([])
    setScanError('')
    setStep('scan')
    setTimeout(() => scanInputRef.current?.focus(), 100)
  }

  // 扫码处理
  const processScan = useCallback((sn) => {
    const trimmed = sn.trim().toUpperCase()
    if (!trimmed || trimmed.length < 3) return
    setScanError('')

    // 检查本批次内重复
    if (scannedList.some(item => item.sn === trimmed)) {
      setScanError(`序列号 ${trimmed} 已在本批次中，已跳过`)
      setScanInput('')
      bufferRef.current = ''
      return
    }

    const newTag = generateTag(scannedList.length)
    setScannedList(prev => [...prev, { sn: trimmed, asset_tag: newTag }])
    setScanInput('')
    bufferRef.current = ''
    setTimeout(() => scanInputRef.current?.focus(), 50)
  }, [scannedList, generateTag])

  const handleScanKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      clearTimeout(timerRef.current)
      const val = bufferRef.current
      bufferRef.current = ''
      setScanInput('')
      if (val.trim()) processScan(val)
      return
    }
    if (e.key.length === 1) {
      bufferRef.current += e.key
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setScanInput(bufferRef.current), SCAN_BUFFER_MS * 10)
    }
  }, [processScan])

  const handleRemoveScan = (index) => {
    setScannedList(prev => {
      const next = prev.filter((_, i) => i !== index)
      // 重新计算后续编号
      return next.map((item, i) => ({ ...item, asset_tag: generateTag(i) }))
    })
  }

  const handleSubmit = async () => {
    if (scannedList.length === 0) { alert('请先扫描至少一个序列号'); return }
    setSubmitting(true)
    const results = []
    for (const item of scannedList) {
      try {
        await axios.post(`${API_URL}/assets/`, {
          asset_tag: item.asset_tag,
          serial_number: item.sn,
          category,
          brand: brand || undefined,
          model: model || undefined,
          po_number: poNumber.trim(),
          status: '闲置',
        })
        results.push({ ...item, success: true })
      } catch (err) {
        results.push({ ...item, success: false, error: err.response?.data?.detail || err.message })
      }
    }
    setSubmitResult(results)
    setSubmitting(false)
    setStep('confirm')
  }

  const successCount = submitResult?.filter(r => r.success).length ?? 0
  const failCount = submitResult?.filter(r => !r.success).length ?? 0

  return (
    <div style={{ maxWidth: 800, margin: '0 auto' }}>
      {/* 顶部导航 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24 }}>
        <button className="btn btn-secondary btn-sm" onClick={onBack}>
          <ArrowLeft size={14} /> 返回扫码工作台
        </button>
        <div>
          <h2 style={{ fontSize: 18, margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <PackagePlus size={18} style={{ color: 'var(--color-primary)' }} />
            批量入库
          </h2>
          <p style={{ fontSize: 12, color: 'var(--color-muted)', margin: '2px 0 0' }}>
            {step === 'setup' ? '第一步：填写入库信息' : step === 'scan' ? `第二步：扫码录入（已扫 ${scannedList.length} 件）` : '第三步：入库结果'}
          </p>
        </div>
      </div>

      {/* 步骤指示器 */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24 }}>
        {[['setup', '1', '填写信息'], ['scan', '2', '扫码录入'], ['confirm', '3', '入库结果']].map(([s, num, label]) => {
          const active = step === s
          const done = (step === 'scan' && s === 'setup') || (step === 'confirm' && (s === 'setup' || s === 'scan'))
          return (
            <div key={s} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{
                  width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700,
                  background: done ? 'var(--color-success)' : active ? 'var(--color-primary)' : 'var(--color-border)',
                  color: (done || active) ? '#fff' : 'var(--color-muted)',
                }}>
                  {done ? '✓' : num}
                </div>
                <span style={{ fontSize: 13, fontWeight: active ? 600 : 400, color: active ? 'var(--color-heading)' : 'var(--color-muted)' }}>
                  {label}
                </span>
              </div>
              {s !== 'confirm' && <div style={{ flex: 1, height: 1, background: 'var(--color-border)', margin: '0 12px' }} />}
            </div>
          )
        })}
      </div>

      {/* ===== 步骤1：填写信息 ===== */}
      {step === 'setup' && (
        <div style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', padding: 24 }}>
          <div className="form-row">
            <div className="form-group">
              <label>品类 *</label>
              <select value={category} onChange={e => setCategory(e.target.value)}>
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
            <div className="form-group">
              <label>PO号 *</label>
              <input type="text" value={poNumber} onChange={e => setPoNumber(e.target.value)}
                placeholder="例如：12000327" pattern="^\d+$" title="PO号必须为纯数字" />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>品牌</label>
              <select value={brand} onChange={e => setBrand(e.target.value)}>
                <option value="">选择品牌（可选）</option>
                {brands.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label>型号</label>
              <input type="text" value={model} onChange={e => setModel(e.target.value)} placeholder="可选" />
            </div>
          </div>
          <div className="form-group">
            <label>
              起始资产编号 *
              <span style={{ fontSize: 11, color: 'var(--color-muted)', marginLeft: 8, fontWeight: 400 }}>
                系统自动建议，可手动修改
              </span>
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input type="text" value={loadingTag ? '加载中...' : startTag}
                onChange={e => setStartTag(e.target.value)}
                placeholder="ZS-NB26-000001"
                style={{ fontFamily: 'var(--font-mono)', flex: 1 }}
                disabled={loadingTag} />
              <button className="btn btn-secondary btn-sm" onClick={() => fetchNextTag(category)} disabled={loadingTag}>
                刷新
              </button>
            </div>
            {startTag && !isValidStartTag && (
              <div style={{ fontSize: 12, color: 'var(--color-danger)', marginTop: 4 }}>格式错误，应为 ZS-XXXX-NNNNNN</div>
            )}
            {startTag && isValidStartTag && (
              <div style={{ fontSize: 12, color: 'var(--color-muted)', marginTop: 4 }}>
                本批次编号将从 <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-primary)' }}>{startTag}</span> 开始顺序递增
              </div>
            )}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
            <button className="btn btn-primary" onClick={handleSetupNext} disabled={loadingTag || !isValidStartTag || !poNumber.trim()}>
              下一步：开始扫码 →
            </button>
          </div>
        </div>
      )}

      {/* ===== 步骤2：扫码录入 ===== */}
      {step === 'scan' && (
        <div>
          {/* 信息摘要条 */}
          <div style={{ display: 'flex', gap: 16, padding: '10px 16px', background: 'var(--color-info-bg)', border: '1px solid var(--color-accent)', borderRadius: 'var(--radius)', marginBottom: 16, fontSize: 13, flexWrap: 'wrap' }}>
            <span>品类：<strong>{category}</strong></span>
            <span>PO号：<strong style={{ fontFamily: 'var(--font-mono)' }}>{poNumber}</strong></span>
            {brand && <span>品牌：<strong>{brand}</strong></span>}
            {model && <span>型号：<strong>{model}</strong></span>}
            <span>起始编号：<strong style={{ fontFamily: 'var(--font-mono)' }}>{startTag}</strong></span>
          </div>

          {/* 扫码输入 */}
          <div className="scan-input-area" style={{ marginBottom: 16 }}>
            <div className="scan-input-card">
              <div className="scan-icon-wrap">
                <Scan size={28} color="#375B81" />
              </div>
              <p className="scan-prompt">扫描序列号（SN）条形码</p>
              <div style={{ width: '100%', maxWidth: 480 }}>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input ref={scanInputRef} type="text" className="scan-sn-input"
                    value={scanInput}
                    onChange={e => { setScanInput(e.target.value); bufferRef.current = e.target.value }}
                    onKeyDown={handleScanKeyDown}
                    placeholder="扫码自动捕获，或手动输入后按 Enter"
                    autoComplete="off" autoCorrect="off" spellCheck={false} />
                  <button className="btn btn-primary" onClick={() => { const v = bufferRef.current || scanInput; bufferRef.current = ''; if (v.trim()) processScan(v) }}
                    disabled={!scanInput.trim()}>
                    添加
                  </button>
                </div>
                {scanError && <div style={{ fontSize: 12, color: 'var(--color-danger)', marginTop: 6 }}>{scanError}</div>}
              </div>
            </div>
          </div>

          {/* 已扫列表 */}
          <div style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', overflow: 'hidden', marginBottom: 16 }}>
            <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-heading)' }}>已扫序列号（{scannedList.length} 件）</span>
              {scannedList.length > 0 && (
                <button className="btn btn-sm btn-secondary" onClick={() => setScannedList([])}>清空</button>
              )}
            </div>
            {scannedList.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--color-muted)', fontSize: 13 }}>
                等待扫码...
              </div>
            ) : (
              <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <thead>
                    <tr style={{ background: 'var(--color-bg)' }}>
                      <th style={thS}>#</th>
                      <th style={thS}>序列号 (SN)</th>
                      <th style={thS}>分配资产编号</th>
                      <th style={thS}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {scannedList.map((item, i) => (
                      <tr key={i} style={{ borderTop: '1px solid var(--color-border)' }}>
                        <td style={tdS}>{i + 1}</td>
                        <td style={{ ...tdS, fontFamily: 'var(--font-mono)' }}>{item.sn}</td>
                        <td style={{ ...tdS, fontFamily: 'var(--font-mono)', color: 'var(--color-primary)', fontWeight: 600 }}>{item.asset_tag}</td>
                        <td style={{ ...tdS, textAlign: 'center' }}>
                          <button className="btn btn-sm btn-danger" onClick={() => handleRemoveScan(i)} title="移除此条">
                            <X size={12} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <button className="btn btn-secondary" onClick={() => setStep('setup')}>← 返回修改信息</button>
            <button className="btn btn-primary" onClick={handleSubmit} disabled={scannedList.length === 0 || submitting}>
              {submitting ? '入库中...' : `确认入库（${scannedList.length} 件）`}
            </button>
          </div>
        </div>
      )}

      {/* ===== 步骤3：入库结果 ===== */}
      {step === 'confirm' && submitResult && (
        <div>
          {/* 结果摘要 */}
          <div style={{
            padding: '16px 20px', borderRadius: 'var(--radius)', marginBottom: 16,
            background: failCount === 0 ? 'var(--color-success-bg)' : 'var(--color-warning-bg)',
            border: `1px solid ${failCount === 0 ? '#A7F3D0' : '#FDE68A'}`,
            display: 'flex', alignItems: 'center', gap: 12,
          }}>
            {failCount === 0
              ? <CheckCircle size={24} style={{ color: 'var(--color-success)', flexShrink: 0 }} />
              : <AlertCircle size={24} style={{ color: 'var(--color-warning)', flexShrink: 0 }} />
            }
            <div>
              <div style={{ fontWeight: 600, fontSize: 15 }}>
                {failCount === 0 ? `全部入库成功！共 ${successCount} 件` : `入库完成：成功 ${successCount} 件，失败 ${failCount} 件`}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-muted)', marginTop: 2 }}>
                品类：{category} · PO号：{poNumber}
              </div>
            </div>
          </div>

          {/* 明细表 */}
          <div style={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', overflow: 'hidden', marginBottom: 16 }}>
            <div style={{ maxHeight: 400, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ background: 'var(--color-bg)', position: 'sticky', top: 0 }}>
                    <th style={thS}>#</th>
                    <th style={thS}>序列号 (SN)</th>
                    <th style={thS}>资产编号</th>
                    <th style={thS}>结果</th>
                  </tr>
                </thead>
                <tbody>
                  {submitResult.map((item, i) => (
                    <tr key={i} style={{ borderTop: '1px solid var(--color-border)', background: item.success ? '#fff' : 'var(--color-danger-bg)' }}>
                      <td style={tdS}>{i + 1}</td>
                      <td style={{ ...tdS, fontFamily: 'var(--font-mono)' }}>{item.sn}</td>
                      <td style={{ ...tdS, fontFamily: 'var(--font-mono)', color: item.success ? 'var(--color-primary)' : 'var(--color-danger)', fontWeight: 600 }}>{item.asset_tag}</td>
                      <td style={tdS}>
                        {item.success
                          ? <span style={{ color: 'var(--color-success)', fontWeight: 600 }}>✓ 成功</span>
                          : <span style={{ color: 'var(--color-danger)', fontSize: 12 }}>✗ {item.error}</span>
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            {failCount > 0 && (
              <button className="btn btn-secondary" onClick={() => {
                setScannedList(submitResult.filter(r => !r.success).map(r => ({ sn: r.sn, asset_tag: r.asset_tag })))
                setSubmitResult(null)
                setStep('scan')
              }}>
                重试失败项
              </button>
            )}
            <button className="btn btn-primary" onClick={() => {
              setStep('setup')
              setScannedList([])
              setSubmitResult(null)
              setPoNumber('')
              fetchNextTag(category)
            }}>
              继续入库
            </button>
            <button className="btn btn-secondary" onClick={onBack}>返回工作台</button>
          </div>
        </div>
      )}
    </div>
  )
}

// 表格样式常量
const thS = { padding: '8px 14px', fontWeight: 600, color: 'var(--color-heading)', textAlign: 'left', borderBottom: '1px solid var(--color-border)', whiteSpace: 'nowrap', fontSize: 12 }
const tdS = { padding: '8px 14px', verticalAlign: 'middle' }

// ========== 原有扫码工作台 ==========
function ScanWorkstation() {
  const {isReadOnly} =useAuth()
  const [mode, setMode] = useState('single')  // 'single' | 'bulk'
  const [scanInput, setScanInput] = useState('')
  const [isProcessing, setIsProcessing] = useState(false)
  const [scanHistory, setScanHistory] = useState([])
  const [showModal, setShowModal] = useState(false)
  const [modalAsset, setModalAsset] = useState(null)
  const [scanHint, setScanHint] = useState(null)
  const [lastResult, setLastResult] = useState(null)

  const inputRef = useRef(null)
  const bufferRef = useRef('')
  const timerRef = useRef(null)

  useEffect(() => {
    if (mode === 'single') {
      inputRef.current?.focus()
    }
    return () => clearTimeout(timerRef.current)
  }, [mode])

  const processScan = useCallback(async (sn) => {
    const trimmed = sn.trim().toUpperCase()
    if (!trimmed || trimmed.length < 3) return
    setScanInput(trimmed)
    setIsProcessing(true)
    setLastResult(null)
    try {
      const res = await axios.get(`${API_URL}/assets/identify-by-sn/${encodeURIComponent(trimmed)}`)
      const data = res.data
      const historyEntry = {
        id: Date.now(), sn: trimmed, action: data.action,
        asset_tag: data.asset?.asset_tag || data.suggested_tag || '-',
        status: data.asset?.status || null, employee: data.asset?.employee_name || null,
        timestamp: new Date().toLocaleTimeString('zh-CN'),
      }
      setScanHistory(prev => [historyEntry, ...prev].slice(0, 50))
      setLastResult(data)
      if (data.action === 'CREATE') {
        setScanHint({ type: 'create', message: `检测到新设备，已根据当前序列生成编号 ${data.suggested_tag}`, suggested_tag: data.suggested_tag })
        setModalAsset({
          asset_tag: data.suggested_tag, serial_number: trimmed,
          category: '', brand: '', model: '', hostname: '',
          mac_address: '', ip_address: '', system_version: '',
          antivirus_software: '', lock_number: '', supervisor: '',
          bios_password: false, tpm_status: false, has_desktop: false,
          employee_name: '', employee_id: '', department: '', status: '闲置', notes: '',
        })
        setShowModal(true)
      } else {
        setScanHint({
          type: data.action === 'UPDATE' ? 'update' : 'view',
          message: data.action === 'UPDATE'
            ? `资产 ${data.asset.asset_tag} 当前使用中（${data.asset.employee_name || '未知'}），可更新信息`
            : `资产 ${data.asset.asset_tag} 当前状态：${data.asset.status}`,
        })
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.message
      setScanHint({ type: 'error', message: `查询失败：${msg}` })
      setScanHistory(prev => [{ id: Date.now(), sn: trimmed, action: 'ERROR', asset_tag: '-', status: null, employee: null, timestamp: new Date().toLocaleTimeString('zh-CN') }, ...prev].slice(0, 50))
    } finally {
      setIsProcessing(false)
      setScanInput('')
      setTimeout(() => { if (!showModal) inputRef.current?.focus() }, 100)
    }
  }, [showModal])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter') {
      clearTimeout(timerRef.current)
      const val = bufferRef.current
      bufferRef.current = ''
      setScanInput('')
      if (val.trim()) processScan(val)
      return
    }
    if (e.key.length === 1) {
      bufferRef.current += e.key
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => setScanInput(bufferRef.current), SCAN_BUFFER_MS * 10)
    }
  }, [processScan])

  const handleInputChange = (e) => { setScanInput(e.target.value); bufferRef.current = e.target.value }
  const handleManualSubmit = (e) => { e.preventDefault(); const val = bufferRef.current || scanInput; bufferRef.current = ''; if (val.trim()) processScan(val) }
  const handleModalClose = () => { setShowModal(false); setModalAsset(null); setScanHint(null); setTimeout(() => inputRef.current?.focus(), 150) }
  const handleModalSave = async (assetData) => {
    try {
      await axios.post(`${API_URL}/assets/`, assetData)
      setShowModal(false); setModalAsset(null)
      setScanHint({ type: 'success', message: `资产 ${assetData.asset_tag} 已成功创建` })
      setScanHistory(prev => prev.map(h => h.sn === assetData.serial_number ? { ...h, action: 'CREATED', asset_tag: assetData.asset_tag } : h))
      setTimeout(() => inputRef.current?.focus(), 150)
    } catch (err) { alert('保存资产失败: ' + (err.response?.data?.detail || err.message)) }
  }

  const actionBadge = (action) => {
    const map = { CREATE: { label: '新设备', color: '#375B81', bg: '#EBF0F8' }, CREATED: { label: '已创建', color: '#3A9E75', bg: '#E8F7F1' }, UPDATE: { label: '使用中', color: '#D4952B', bg: '#FDF3E3' }, VIEW: { label: '已存在', color: '#8E9EA4', bg: '#F2F4F5' }, ERROR: { label: '错误', color: '#E05252', bg: '#FDEAEA' } }
    const s = map[action] || map.VIEW
    return <span style={{ padding: '2px 8px', borderRadius: 9999, fontSize: 11, fontWeight: 600, color: s.color, background: s.bg, border: `1px solid ${s.color}33` }}>{s.label}</span>
  }

  // 批量入库模式
  if (mode === 'bulk') return <BulkInbound onBack={() => setMode('single')} />

  if (isReadOnly) {
    return (
      <div classname="scan-workstation">
        <div classname="scan-header">
          <h2><scan size={20} style={{ verticalAlign: 'middle', marginRight:8}} />扫码工作台</h2>
        </div>
        <div style={{ textAlign: 'center', padding: '80px 20px', background: 'var(--color-surface)', borderRadius: 'var(--radius)', border: '1px soild var(--color-border)', marginTop: 20}}>
         <AlertCircle size={48} style={{color: 'var(--color-muted)', marginBottom: 16}} />
         <h3 style={{color: 'var(--color-heading)', marginBottom:8 }}>只读模式限制</h3>
         <p style={{color: 'var(--color-muted)'}}>您当前为只读权限，无法使用扫码工作台进行资产录入或状态修改。</p>
        </div>
      </div>
    )
  }

  return (
    <div className="scan-workstation">
      <div className="scan-header">
        <div>
          <h2><Scan size={20} style={{ verticalAlign: 'middle', marginRight: 8 }} />扫码工作台</h2>
          <p style={{ color: '#8E9EA4', margin: '4px 0 0', fontSize: 13 }}>使用扫码枪扫描设备 SN 条形码，自动识别并创建资产</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary btn-sm" onClick={() => setMode('bulk')}>
            <PackagePlus size={14} /> 批量入库
          </button>
          <button className="btn btn-secondary btn-sm" onClick={() => setScanHistory([])} title="清空本次记录">
            <Trash2 size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />清空记录
          </button>
        </div>
      </div>

      <div className="scan-input-area">
        <div className="scan-input-card">
          <div className="scan-icon-wrap">
            {isProcessing ? <div className="scan-spinner" /> : <Scan size={32} color="#375B81" />}
          </div>
          <p className="scan-prompt">{isProcessing ? '正在识别...' : '请扫描设备 SN 条形码'}</p>
          <form onSubmit={handleManualSubmit} style={{ width: '100%', maxWidth: 480 }}>
            <div style={{ display: 'flex', gap: 8 }}>
              <input ref={inputRef} type="text" className="scan-sn-input" value={scanInput}
                onChange={handleInputChange} onKeyDown={handleKeyDown}
                placeholder="SN 自动捕获，或手动输入后按 Enter"
                autoComplete="off" autoCorrect="off" spellCheck={false} disabled={isProcessing} />
              <button type="submit" className="btn btn-primary" disabled={isProcessing || !scanInput.trim()}>查询</button>
            </div>
          </form>
        </div>
        {scanHint && (
          <div className={`scan-hint scan-hint-${scanHint.type}`}>
            {scanHint.type === 'create' && <Info size={16} />}
            {scanHint.type === 'success' && <CheckCircle size={16} />}
            {scanHint.type === 'error' && <AlertCircle size={16} />}
            {(scanHint.type === 'update' || scanHint.type === 'view') && <Clock size={16} />}
            <span>{scanHint.message}</span>
          </div>
        )}
        {lastResult && lastResult.action !== 'CREATE' && lastResult.asset && (
          <div className="scan-result-card">
            <div className="scan-result-row"><span className="scan-result-label">资产编号</span><span className="scan-result-value font-data">{lastResult.asset.asset_tag}</span></div>
            <div className="scan-result-row"><span className="scan-result-label">品类</span><span className="scan-result-value">{lastResult.asset.category || '-'}</span></div>
            <div className="scan-result-row"><span className="scan-result-label">品牌 / 型号</span><span className="scan-result-value">{[lastResult.asset.brand, lastResult.asset.model].filter(Boolean).join(' ') || '-'}</span></div>
            <div className="scan-result-row"><span className="scan-result-label">状态</span><span className="scan-result-value">{lastResult.asset.status}</span></div>
            {lastResult.asset.employee_name && (
              <div className="scan-result-row"><span className="scan-result-label">使用人</span><span className="scan-result-value">{lastResult.asset.employee_name}（{lastResult.asset.department || '-'}）</span></div>
            )}
          </div>
        )}
      </div>

      <div className="scan-history-section">
        <h3 style={{ fontSize: 14, fontWeight: 600, color: '#1F3247', marginBottom: 12 }}>本次扫码记录（{scanHistory.length} 条）</h3>
        {scanHistory.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '32px 0', color: '#8E9EA4', fontSize: 13 }}>暂无记录，等待扫码...</div>
        ) : (
          <table className="scan-history-table">
            <thead><tr><th>时间</th><th>序列号 (SN)</th><th>资产编号</th><th>状态</th><th>使用人</th><th>识别结果</th></tr></thead>
            <tbody>
              {scanHistory.map(h => (
                <tr key={h.id}>
                  <td style={{ color: '#8E9EA4', fontSize: 12 }}>{h.timestamp}</td>
                  <td><span className="font-data" style={{ fontSize: 12 }}>{h.sn}</span></td>
                  <td><span className="font-data" style={{ fontSize: 12 }}>{h.asset_tag}</span></td>
                  <td style={{ fontSize: 12 }}>{h.status || '-'}</td>
                  <td style={{ fontSize: 12 }}>{h.employee || '-'}</td>
                  <td>{actionBadge(h.action)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {showModal && modalAsset && (
        <AssetModal asset={modalAsset} onClose={handleModalClose} onSave={handleModalSave}
          scanBanner={scanHint?.type === 'create' ? scanHint.message : null} />
      )}
    </div>
  )
}

export default ScanWorkstation
