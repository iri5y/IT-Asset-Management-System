import { useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle,
  Download,
  FileSpreadsheet,
  LoaderCircle,
  Play,
  Upload,
  XCircle,
} from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''
const MAX_FILE_SIZE = 10 * 1024 * 1024
const STEPS = ['上传', '预览', '确认', '结果']
const FIELD_META = {
  department: { label: '部门', type: 'DEPARTMENT' },
  brand: { label: '品牌', type: 'BRAND' },
  location: { label: '位置', type: 'LOCATION' },
}
const CLASSIFICATION_LABELS = {
  VALID: '有效',
  MAPPING_REQUIRED: '待确认',
  DUPLICATE: '重复',
  ERROR: '错误',
}
const DECISION_LABELS = {
  INSERT: '新增',
  UPDATE: '更新',
  REPLACE: '替换',
  SKIP: '跳过',
}
const RESULT_STATUS_LABELS = {
  SUCCESS: '成功',
  SKIPPED: '已跳过',
  FAILED: '失败',
}
const ERROR_TYPE_LABELS = {
  FORMAT: '格式错误',
  VALIDATION: '校验错误',
  MAPPING: '映射问题',
  CONFLICT: '数据冲突',
  SYSTEM: '系统错误',
}
const STRATEGY_LABELS = {
  INSERT_ONLY: '仅新增（重复项跳过）',
  UPDATE_EXISTING: '更新已有项',
  REPLACE_EXISTING: '替换已有项',
  DRY_RUN: '干运行',
}
const WARNING_TYPE_LABELS = {
  EXTRA_COLUMNS: '未知列提示',
  POLICY_SKIP: '策略跳过',
  CONFLICT: '重复项跳过',
  WAREHOUSE_NOT_FOUND: '库存未同步',
}

function issueKey(field, rawValue) {
  return `${field}:${rawValue}`
}

function normalizeDetail(detail) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((item) => item?.msg || String(item)).join('；')
  if (detail && typeof detail === 'object') {
    const issues = Array.isArray(detail.errors)
      ? detail.errors.map((item) => {
          const row = item?.row_number ? `第 ${item.row_number} 行` : '未知行'
          const field = item?.field ? `【${item.field}】` : ''
          return `${row}${field}：${item?.reason || '业务规则校验失败'}`
        }).join('；')
      : ''
    return [detail.message || detail.detail, issues].filter(Boolean).join('；') || JSON.stringify(detail)
  }
  return ''
}

function apiError(error, fallback) {
  const data = error.response?.data
  const status = error.response?.status
  const detail = normalizeDetail(data?.detail) || fallback
  const requestId = data?.request_id || data?.detail?.request_id || ''
  const hasBusinessErrors = Array.isArray(data?.detail?.errors)

  if (status === 404) return { message: '导入会话已过期或不存在，请返回上传步骤重新上传文件。', requestId }
  if (hasBusinessErrors) return { message: detail, requestId }
  if (status === 409) return { message: `当前会话状态不允许此操作：${detail}。请勿重复提交，必要时重新上传文件。`, requestId }
  return { message: detail, requestId }
}

function ErrorNotice({ error }) {
  if (!error) return null
  return (
    <div className="import-wizard-error" role="alert">
      <AlertTriangle size={17} />
      <div>
        <div>{error.message}</div>
        {error.requestId && <div className="import-wizard-request-id">请求 ID：{error.requestId}</div>}
      </div>
    </div>
  )
}

function StepIndicator({ currentStep }) {
  return (
    <ol className="import-wizard-steps" aria-label="导入进度">
      {STEPS.map((label, index) => {
        const step = index + 1
        const state = step === currentStep ? 'active' : step < currentStep ? 'complete' : ''
        return (
          <li className={state} key={label} aria-current={step === currentStep ? 'step' : undefined}>
            <span>{step < currentStep ? '✓' : step}</span>
            <strong>{label}</strong>
          </li>
        )
      })}
    </ol>
  )
}

function SummaryCards({ summary }) {
  const cards = [
    ['VALID', summary?.valid || 0],
    ['MAPPING_REQUIRED', summary?.mapping_required || 0],
    ['DUPLICATE', summary?.duplicate || 0],
    ['ERROR', summary?.error || 0],
  ]
  return (
    <div className="import-wizard-summary">
      {cards.map(([type, count]) => (
        <div className={`import-wizard-summary-card is-${type.toLowerCase()}`} key={type}>
          <span>{CLASSIFICATION_LABELS[type]}</span>
          <strong>{count}</strong>
        </div>
      ))}
    </div>
  )
}

function PreviewTable({ records }) {
  return (
    <div className="import-wizard-table-wrap">
      <table className="import-wizard-table">
        <thead>
          <tr>
            <th>行号</th>
            <th>资产编号</th>
            <th>分类</th>
            <th>校验错误 / 映射问题 / 重复信息</th>
          </tr>
        </thead>
        <tbody>
          {records.length === 0 ? (
            <tr><td colSpan="4" className="import-wizard-empty">文件中没有数据行</td></tr>
          ) : records.map((record) => {
            const messages = [
              ...(record.validation_errors || []).map((item) => `${item.field || '字段'}：${item.message || item}`),
              ...(record.resolver_issues || []).map((item) => `${FIELD_META[item.field]?.label || item.field}「${item.raw_value}」：${item.issue_type}`),
            ]
            if (record.duplicate_info) {
              const duplicate = record.duplicate_info
              messages.push(`与现有资产 ${duplicate.asset_tag} 的 ${duplicate.conflict_field} 冲突（状态：${duplicate.status}）`)
            }
            return (
              <tr key={`${record.row_number}-${record.asset_tag || ''}`}>
                <td>{record.row_number}</td>
                <td className="font-data">{record.asset_tag || '—'}</td>
                <td><span className={`import-wizard-badge is-${record.classification.toLowerCase()}`}>{CLASSIFICATION_LABELS[record.classification] || record.classification}</span></td>
                <td>{messages.length ? messages.map((message, index) => <div key={index}>{message}</div>) : '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ImportWizard({ onClose, onImportSuccess }) {
  const [step, setStep] = useState(1)
  const [file, setFile] = useState(null)
  const [parseResult, setParseResult] = useState(null)
  const [summary, setSummary] = useState(null)
  const [duplicatePolicy, setDuplicatePolicy] = useState('INSERT_ONLY')
  const [mappingSelections, setMappingSelections] = useState({})
  const [candidates, setCandidates] = useState({ department: [], brand: [], location: [] })
  const [mappingApplied, setMappingApplied] = useState(false)
  const [readyToExecute, setReadyToExecute] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState('')
  const fileInputRef = useRef(null)

  const mappingIssues = useMemo(() => {
    const unique = new Map()
    for (const record of parseResult?.records || []) {
      for (const issue of record.resolver_issues || []) {
        const key = issueKey(issue.field, issue.raw_value)
        if (!unique.has(key)) unique.set(key, { ...issue, key })
      }
    }
    return [...unique.values()]
  }, [parseResult])

  const allMappingsHandled = mappingIssues.every((issue) => Boolean(mappingSelections[issue.key]))

  useEffect(() => {
    if (step !== 3 || mappingIssues.length === 0) return
    const fields = new Set(mappingIssues.map((issue) => issue.field))
    let cancelled = false

    async function loadCandidates() {
      setBusy('candidates')
      setError(null)
      try {
        const requests = []
        if (fields.has('department')) requests.push(axios.get(`${API_URL}/departments/flat`).then((res) => ['department', res.data]))
        if (fields.has('brand')) requests.push(axios.get(`${API_URL}/brands/`).then((res) => ['brand', res.data]))
        if (fields.has('location')) {
          requests.push(Promise.all([
            axios.get(`${API_URL}/locations/`),
            axios.get(`${API_URL}/office-locations/`),
          ]).then(([warehouse, office]) => ['location', [
            ...warehouse.data.map((item) => ({ ...item, display: `库房：${item.name}` })),
            ...office.data.map((item) => ({ ...item, display: `办公室：${item.name}` })),
          ]]))
        }
        const loaded = await Promise.all(requests)
        if (!cancelled) setCandidates((current) => ({ ...current, ...Object.fromEntries(loaded) }))
      } catch (requestError) {
        if (!cancelled) setError(apiError(requestError, '主数据候选加载失败，请重试。'))
      } finally {
        if (!cancelled) setBusy('')
      }
    }

    loadCandidates()
    return () => { cancelled = true }
  }, [step, mappingIssues])

  const validateFile = (selected) => {
    if (!selected.name.toLowerCase().endsWith('.xlsx')) return '仅支持 .xlsx 格式文件'
    if (selected.size > MAX_FILE_SIZE) return '文件大小不能超过 10MB'
    return ''
  }

  const selectFile = (selected) => {
    if (!selected) return
    const validationError = validateFile(selected)
    if (validationError) {
      setFile(null)
      setError({ message: validationError, requestId: '' })
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }
    setFile(selected)
    setError(null)
  }

  const resetToUpload = () => {
    setStep(1)
    setFile(null)
    setParseResult(null)
    setSummary(null)
    setDuplicatePolicy('INSERT_ONLY')
    setMappingSelections({})
    setMappingApplied(false)
    setReadyToExecute(false)
    setResult(null)
    setError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleDownloadTemplate = async () => {
    if (busy) return
    setBusy('template')
    setError(null)
    try {
      const response = await axios.get(`${API_URL}/assets/import-template`, { responseType: 'blob' })
      const url = window.URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = '资产导入模板.xlsx'
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (requestError) {
      setError(apiError(requestError, '模板下载失败，请确认登录状态后重试。'))
    } finally {
      setBusy('')
    }
  }

  const handleParse = async () => {
    if (!file || busy) return
    setBusy('parse')
    setError(null)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const response = await axios.post(`${API_URL}/assets/import/parse`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setParseResult(response.data)
      setSummary(response.data.preview_summary)
      setStep(2)
    } catch (requestError) {
      setError(apiError(requestError, '文件解析失败，请检查模板和数据格式后重试。'))
    } finally {
      setBusy('')
    }
  }

  const handleApplyMapping = async () => {
    if (busy || !allMappingsHandled) return
    setBusy('mapping')
    setError(null)
    const mappingEntries = mappingIssues.map((issue) => {
      const selection = mappingSelections[issue.key]
      if (selection === 'skip') {
        return {
          raw_value: issue.raw_value,
          field_type: FIELD_META[issue.field].type,
          action: 'skip',
        }
      }
      const targetIndex = Number(selection.split(':')[1])
      const target = candidates[issue.field][targetIndex]
      return {
        raw_value: issue.raw_value,
        field_type: FIELD_META[issue.field].type,
        resolved_id: target.id,
        resolved_name: target.name,
        action: 'map_existing',
      }
    })

    try {
      const response = await axios.post(`${API_URL}/assets/import/apply-mapping`, {
        session_id: parseResult.session_id,
        mapping_entries: mappingEntries,
        duplicate_policy: duplicatePolicy,
      })
      setSummary(response.data.preview_summary)
      setReadyToExecute(response.data.ready_to_execute)
      setMappingApplied(response.data.ready_to_execute)
      if (!response.data.ready_to_execute) {
        setError({
          message: '仍有映射问题或数据错误未解决。选择“跳过”会保留 MAPPING_REQUIRED，当前会话不能执行；请改为映射到已有主数据。',
          requestId: response.data.request_id || '',
        })
      }
    } catch (requestError) {
      setError(apiError(requestError, '应用映射失败，请检查选择后重试。'))
    } finally {
      setBusy('')
    }
  }

  const handleExecute = async () => {
    if (busy || !readyToExecute) return
    setBusy('execute')
    setError(null)
    try {
      const response = await axios.post(`${API_URL}/assets/import/execute`, {
        session_id: parseResult.session_id,
        dry_run: false,
      })
      setResult({ ...response.data.result, request_id: response.data.request_id })
      setStep(4)
      if (response.data.result.success_count > 0) onImportSuccess?.()
    } catch (requestError) {
      setError(apiError(requestError, '执行导入失败，请确认会话状态后重试。'))
    } finally {
      setBusy('')
    }
  }

  const renderUpload = () => (
    <>
      <div className="import-wizard-template-row">
        <button className="btn btn-secondary" onClick={handleDownloadTemplate} disabled={Boolean(busy)}>
          {busy === 'template' ? <LoaderCircle className="import-wizard-spin" size={15} /> : <Download size={15} />}
          下载导入模板
        </button>
        <span>请按标准列头填写，仅支持 .xlsx 文件</span>
      </div>
      <div
        className={`import-wizard-dropzone ${file ? 'has-file' : ''}`}
        onClick={() => !busy && fileInputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          if (!busy) selectFile(event.dataTransfer.files[0])
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(event) => {
          if ((event.key === 'Enter' || event.key === ' ') && !busy) fileInputRef.current?.click()
        }}
      >
        <Upload size={32} />
        <strong>{file ? file.name : '点击或拖拽上传 .xlsx 文件'}</strong>
        <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : '最大 10MB'}</span>
        <input ref={fileInputRef} type="file" accept=".xlsx" hidden onChange={(event) => selectFile(event.target.files[0])} />
      </div>
      <ErrorNotice error={error} />
    </>
  )

  const renderPreview = () => (
    <>
      <div className="import-wizard-section-heading">
        <div>
          <h3>解析预览</h3>
          <p>共 {summary?.total || 0} 行，请在写入前检查分类和逐行问题。</p>
        </div>
        {parseResult?.request_id && <span className="import-wizard-request-id">请求 ID：{parseResult.request_id}</span>}
      </div>
      <SummaryCards summary={summary} />
      {(parseResult?.warnings || []).length > 0 && (
        <div className="import-wizard-warning">
          <AlertTriangle size={16} />
          <span>解析产生 {parseResult.warnings.length} 条提示；{parseResult.inferred_category ? `已从文件名推断品类为「${parseResult.inferred_category}」。` : '请核对预览数据。'}</span>
        </div>
      )}
      <PreviewTable records={parseResult?.records || []} />
      <ErrorNotice error={error} />
    </>
  )

  const renderMapping = () => (
    <>
      <div className="import-wizard-section-heading">
        <div>
          <h3>主数据映射与重复策略</h3>
          <p>{mappingIssues.length ? `共 ${mappingIssues.length} 个唯一主数据值需要处理。` : '无需主数据映射；仍需确认重复策略并应用空映射。'}</p>
        </div>
      </div>

      {mappingIssues.length > 0 && (
        <div className="import-wizard-mapping-list">
          {mappingIssues.map((issue) => (
            <div className="import-wizard-mapping-item" key={issue.key}>
              <div>
                <strong>{FIELD_META[issue.field]?.label || issue.field}</strong>
                <span>Excel 原值：{issue.raw_value}</span>
                <small>{issue.issue_type}{issue.candidates?.length ? `；解析候选：${issue.candidates.join('、')}` : ''}</small>
              </div>
              <select
                value={mappingSelections[issue.key] || ''}
                disabled={mappingApplied || busy === 'candidates'}
                onChange={(event) => setMappingSelections((current) => ({ ...current, [issue.key]: event.target.value }))}
                aria-label={`映射${issue.raw_value}`}
              >
                <option value="">请选择处理方式</option>
                {(candidates[issue.field] || []).map((candidate, index) => (
                  <option key={`${candidate.id}-${index}`} value={`${candidate.id}:${index}`}>
                    {candidate.display || candidate.name}
                  </option>
                ))}
                <option value="skip">跳过（将无法执行该会话）</option>
              </select>
            </div>
          ))}
        </div>
      )}

      <fieldset className="import-wizard-policy" disabled={mappingApplied}>
        <legend>重复数据处理策略</legend>
        {[
          ['INSERT_ONLY', '跳过重复项', '仅插入非重复有效记录，重复项不写入'],
          ['UPDATE_EXISTING', '更新已有项', '保留现有资产编号，更新本次导入提供的其他字段'],
          ['REPLACE_EXISTING', '替换已有项', '完整覆盖已有资产的导入字段（包括资产编号）'],
        ].map(([value, title, description]) => (
          <label className={duplicatePolicy === value ? 'selected' : ''} key={value}>
            <input type="radio" name="duplicate-policy" value={value} checked={duplicatePolicy === value} onChange={(event) => setDuplicatePolicy(event.target.value)} />
            <span><strong>{title}</strong><small>{description}</small></span>
          </label>
        ))}
      </fieldset>

      {mappingApplied && readyToExecute && (
        <div className="import-wizard-ready"><CheckCircle size={17} />映射和策略已确认，可以执行导入。</div>
      )}
      {busy === 'candidates' && <div className="import-wizard-loading"><LoaderCircle className="import-wizard-spin" size={17} />正在加载主数据候选...</div>}
      <ErrorNotice error={error} />
    </>
  )

  const renderResult = () => {
    const statistics = result?.statistics || {}
    const categoryEntries = Object.entries(statistics.by_category || {})
    const statusEntries = Object.entries(statistics.by_status || {})
    const errorEntries = Object.entries(statistics.by_error_type || {})
    const warehouseSynced = statistics.warehouse_synced || []
    const decisionStats = statistics.by_decision || statistics.decision_counts || {}
    const resultErrors = result?.errors || []
    const resultWarnings = result?.warnings || []
    const hasDecisionStats = Boolean(result) && (
      Object.keys(decisionStats).length > 0 || [
        'inserted_count', 'updated_count', 'replaced_count', 'skipped_count', 'failed_count',
      ].some((key) => Object.prototype.hasOwnProperty.call(result, key))
    )

    return (
      <>
        <div className="import-wizard-result-heading">
          {result?.fail_count > 0 ? <XCircle size={28} /> : <CheckCircle size={28} />}
          <div>
            <h3>{result?.dry_run ? '干运行验证完成' : '导入执行完成'}</h3>
            {result?.message && <p>{result.message}</p>}
            {result?.strategy && <p>执行策略：{STRATEGY_LABELS[result.strategy] || result.strategy}</p>}
            {result?.request_id && <span className="import-wizard-request-id">请求 ID：{result.request_id}</span>}
          </div>
        </div>
        {result?.dry_run && (
          <div className="import-wizard-dry-run" role="status">
            <AlertTriangle size={17} />
            <span>这是干运行结果：所有资产、库存和成功审计变更均已回滚，不会写入数据库。</span>
          </div>
        )}
        <div className="import-wizard-result-counts">
          <div><strong>{result?.success_count ?? 0}</strong><span>成功</span></div>
          <div><strong>{result?.skip_count ?? 0}</strong><span>跳过</span></div>
          <div><strong>{result?.fail_count ?? 0}</strong><span>失败</span></div>
        </div>

        {hasDecisionStats && (
          <section className="import-wizard-result-section">
            <h4>决策统计（总行数：{result?.total_rows ?? 0}）</h4>
            <div className="import-wizard-decision-counts">
              <div><strong>{decisionStats.INSERT ?? result?.inserted_count ?? 0}</strong><span>新增决策</span></div>
              <div><strong>{decisionStats.UPDATE ?? result?.updated_count ?? 0}</strong><span>更新决策</span></div>
              <div><strong>{decisionStats.REPLACE ?? result?.replaced_count ?? 0}</strong><span>替换决策</span></div>
              <div><strong>{decisionStats.SKIP ?? result?.skipped_count ?? result?.skip_count ?? 0}</strong><span>跳过决策</span></div>
              <div><strong>{result?.failed_count ?? result?.fail_count ?? 0}</strong><span>执行失败</span></div>
            </div>
          </section>
        )}

        {(categoryEntries.length > 0 || statusEntries.length > 0 || errorEntries.length > 0) && (
          <div className="import-wizard-distributions">
            {categoryEntries.length > 0 && (
              <section className="import-wizard-result-section">
                <h4>品类分布</h4>
                <dl>{categoryEntries.map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count}</dd></div>)}</dl>
              </section>
            )}
            {statusEntries.length > 0 && (
              <section className="import-wizard-result-section">
                <h4>状态分布</h4>
                <dl>{statusEntries.map(([label, count]) => <div key={label}><dt>{label}</dt><dd>{count}</dd></div>)}</dl>
              </section>
            )}
            {errorEntries.length > 0 && (
              <section className="import-wizard-result-section">
                <h4>错误类型分布</h4>
                <dl>{errorEntries.map(([label, count]) => <div key={label}><dt>{ERROR_TYPE_LABELS[label] || label}</dt><dd>{count}</dd></div>)}</dl>
              </section>
            )}
          </div>
        )}

        {(resultErrors.length > 0 || resultWarnings.length > 0) && (
          <section className="import-wizard-result-section">
            <h4>错误与提示</h4>
            <div className="import-wizard-issue-list">
              {resultErrors.map((item, index) => (
                <div className="is-error" key={`error-${item.row_number}-${index}`}>
                  <strong>第 {item.row_number} 行 · {ERROR_TYPE_LABELS[item.error_type] || item.error_type || '错误'}</strong>
                  <span>{item.message || '该记录无法执行'}</span>
                </div>
              ))}
              {resultWarnings.map((item, index) => (
                <div className="is-warning" key={`warning-${item.row_number}-${index}`}>
                  <strong>第 {item.row_number} 行 · {WARNING_TYPE_LABELS[item.warning_type] || '提示'}</strong>
                  <span>{item.message || '该记录已跳过'}</span>
                </div>
              ))}
            </div>
          </section>
        )}

        {warehouseSynced.length > 0 && (
          <section className="import-wizard-result-section">
            <h4>库存同步明细</h4>
            <div className="import-wizard-table-wrap">
              <table className="import-wizard-table">
                <thead><tr><th>库存标识</th><th>库存名称</th><th>映射品类</th><th>可用量（前）</th><th>可用量（后）</th><th>已分配（前）</th><th>已分配（后）</th><th>变化量</th><th>提交状态</th></tr></thead>
                <tbody>{warehouseSynced.map((entry, index) => (
                  <tr key={`${entry.warehouse_asset_id ?? 'unknown'}-${index}`}>
                    <td>{entry.warehouse_asset_id ?? '—'}</td>
                    <td>{entry.warehouse_asset_name || '—'}</td>
                    <td>{entry.warehouse_category || '—'}</td>
                    <td>{entry.before_available ?? '—'}</td>
                    <td>{entry.after_available ?? '—'}</td>
                    <td>{entry.before_allocated ?? '—'}</td>
                    <td>{entry.after_allocated ?? '—'}</td>
                    <td>{typeof entry.delta === 'number' && entry.delta > 0 ? `+${entry.delta}` : (entry.delta ?? '—')}</td>
                    <td>{entry.dry_run ? '干运行（未提交）' : entry.rolled_back ? '已回滚' : entry.committed === true ? '已提交' : entry.committed === false ? '未提交' : '已执行'}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </section>
        )}

        {(result?.records || []).length > 0 && (
          <section className="import-wizard-result-section">
            <h4>逐行结果</h4>
            <div className="import-wizard-table-wrap">
              <table className="import-wizard-table">
                <thead><tr><th>行号</th><th>资产编号</th><th>品类</th><th>资产状态</th><th>决策</th><th>结果</th><th>说明</th></tr></thead>
                <tbody>
                  {(result?.records || []).map((record) => (
                    <tr key={`${record.row_number}-${record.asset_tag || ''}`}>
                      <td>{record.row_number}</td>
                      <td className="font-data">{record.asset_tag || '—'}</td>
                      <td>{record.category || '—'}</td>
                      <td>{record.asset_status || '—'}</td>
                      <td>{DECISION_LABELS[record.decision] || record.decision}</td>
                      <td><span className={`import-wizard-badge is-${String(record.status || '').toLowerCase()}`}>{RESULT_STATUS_LABELS[record.status] || record.status || '未知'}</span></td>
                      <td>{record.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </>
    )
  }

  const renderFooter = () => {
    if (step === 1) return (
      <>
        <button className="btn btn-secondary" onClick={onClose}>取消</button>
        <button className="btn btn-primary" onClick={handleParse} disabled={!file || Boolean(busy)}>
          {busy === 'parse' ? <><LoaderCircle className="import-wizard-spin" size={15} />解析中...</> : <><Upload size={15} />上传并解析</>}
        </button>
      </>
    )
    if (step === 2) return (
      <>
        <button className="btn btn-secondary" onClick={onClose}>取消</button>
        <button className="btn btn-secondary" onClick={resetToUpload}><ArrowLeft size={15} />返回上传</button>
        <button className="btn btn-primary" onClick={() => { setError(null); setStep(3) }}>继续映射/策略</button>
      </>
    )
    if (step === 3) return (
      <>
        <button className="btn btn-secondary" onClick={onClose}>取消</button>
        {!mappingApplied && <button className="btn btn-secondary" onClick={() => { setError(null); setStep(2) }} disabled={Boolean(busy)}><ArrowLeft size={15} />返回预览</button>}
        {!mappingApplied ? (
          <button className="btn btn-primary" onClick={handleApplyMapping} disabled={Boolean(busy) || !allMappingsHandled}>
            {busy === 'mapping' ? <><LoaderCircle className="import-wizard-spin" size={15} />应用中...</> : '应用映射并确认策略'}
          </button>
        ) : (
          <button className="btn btn-primary" onClick={handleExecute} disabled={Boolean(busy) || !readyToExecute}>
            {busy === 'execute' ? <><LoaderCircle className="import-wizard-spin" size={15} />执行中...</> : <><Play size={15} />确认执行导入</>}
          </button>
        )}
      </>
    )
    return (
      <>
        <button className="btn btn-secondary" onClick={resetToUpload}>再次导入</button>
        <button className="btn btn-primary" onClick={onClose}>关闭</button>
      </>
    )
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content import-wizard-modal" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="import-wizard-title">
        <div className="modal-header">
          <h2 id="import-wizard-title"><FileSpreadsheet size={19} />资产导入</h2>
          <button className="close-btn" onClick={onClose} aria-label="关闭">&times;</button>
        </div>
        <StepIndicator currentStep={step} />
        <div className="modal-body import-wizard-body">
          {step === 1 && renderUpload()}
          {step === 2 && renderPreview()}
          {step === 3 && renderMapping()}
          {step === 4 && renderResult()}
        </div>
        <div className="modal-footer import-wizard-footer">{renderFooter()}</div>
      </div>
    </div>
  )
}

export default ImportWizard
