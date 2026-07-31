import { useState, useRef } from 'react'
import axios from 'axios'
import { Upload, Download, CheckCircle, XCircle, FileSpreadsheet } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

/**
 * 资产批量导入对话框
 *
 * Props:
 *   onClose: () => void          — 关闭对话框
 *   onImportSuccess: () => void  — 导入成功后的回调（用于刷新资产列表）
 */
function ImportModal({ onClose, onImportSuccess }) {
  const [file, setFile] = useState(null)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const fileInputRef = useRef(null)

  // 处理文件选择
  const handleFileChange = (e) => {
    const selected = e.target.files[0]
    if (!selected) return

    if (!selected.name.toLowerCase().endsWith('.xlsx')) {
      setError('仅支持 .xlsx 格式文件')
      setFile(null)
      return
    }
    setError('')
    setResult(null)
    setFile(selected)
  }

  // 处理拖拽上传
  const handleDrop = (e) => {
    e.preventDefault()
    const dropped = e.dataTransfer.files[0]
    if (!dropped) return
    if (!dropped.name.toLowerCase().endsWith('.xlsx')) {
      setError('仅支持 .xlsx 格式文件')
      return
    }
    setError('')
    setResult(null)
    setFile(dropped)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
  }

  // 下载导入模板
  const handleDownloadTemplate = async () => {
    try {
      const response = await axios.get(`${API_URL}/assets/import-template`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(new Blob([response.data]))
      const link = document.createElement('a')
      link.href = url
      link.setAttribute('download', 'asset_import_template.xlsx')
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      setError('模板下载失败，请重试')
    }
  }

  // 执行导入
  const handleImport = async () => {
    if (!file) {
      setError('请先选择要导入的 .xlsx 文件')
      return
    }

    setImporting(true)
    setError('')
    setResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await axios.post(`${API_URL}/assets/import`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setResult(response.data)
      // 只要有成功写入，就触发刷新
      if (response.data.success_count > 0 && onImportSuccess) {
        onImportSuccess()
      }
    } catch (err) {
      const detail = err.response?.data?.detail
      setError(detail || '导入失败，请检查文件格式后重试')
    } finally {
      setImporting(false)
    }
  }

  // 重置，准备再次导入
  const handleReset = () => {
    setFile(null)
    setResult(null)
    setError('')
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: '640px', width: '95%' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 标题栏 */}
        <div className="modal-header">
          <h2>
            <FileSpreadsheet size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} />
            批量导入资产
          </h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body">
          {/* 下载模板 */}
          <div style={{ marginBottom: 16 }}>
            <button
              className="btn btn-secondary"
              onClick={handleDownloadTemplate}
              style={{ fontSize: 13 }}
            >
              <Download size={14} />
              下载导入模板
            </button>
            <span style={{ marginLeft: 10, fontSize: 12, color: 'var(--color-muted)' }}>
              请按模板格式填写数据后上传
            </span>
          </div>

          {/* 文件选择区域 */}
          {!result && (
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: '2px dashed var(--color-border)',
                borderRadius: 8,
                padding: '28px 20px',
                textAlign: 'center',
                cursor: 'pointer',
                background: file ? 'var(--color-info-bg)' : 'var(--color-bg)',
                transition: 'background 0.15s',
                marginBottom: 12,
              }}
            >
              <Upload size={28} style={{ color: 'var(--color-muted)', marginBottom: 8 }} />
              <div style={{ fontSize: 14, color: 'var(--color-body)', marginBottom: 4 }}>
                {file ? (
                  <span style={{ color: 'var(--color-primary)', fontWeight: 500 }}>
                    已选择：{file.name}
                  </span>
                ) : (
                  '点击或拖拽上传 .xlsx 文件'
                )}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-muted)' }}>最大 10MB</div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".xlsx"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div
              style={{
                background: 'var(--color-danger-bg)',
                color: 'var(--color-danger-text)',
                borderRadius: 6,
                padding: '10px 14px',
                fontSize: 13,
                marginBottom: 12,
              }}
            >
              {error}
            </div>
          )}

          {/* 导入结果 */}
          {result && (
            <div>
              {/* 结果摘要 */}
              <div
                style={{
                  display: 'flex',
                  gap: 16,
                  marginBottom: 16,
                  padding: '12px 16px',
                  background: result.success_count > 0 ? 'var(--color-success-bg)' : 'var(--color-warning-bg)',
                  borderRadius: 8,
                  alignItems: 'center',
                }}
              >
                {result.success_count > 0 ? (
                  <CheckCircle size={20} style={{ color: 'var(--color-success)', flexShrink: 0 }} />
                ) : (
                  <XCircle size={20} style={{ color: 'var(--color-danger)', flexShrink: 0 }} />
                )}
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>
                    {result.message}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--color-muted)' }}>
                    总行数：{result.total_rows} &nbsp;|&nbsp;
                    成功：{result.success_count} &nbsp;|&nbsp;
                    失败：{result.failed_count}
                  </div>
                </div>
                <button
                  className="btn btn-secondary"
                  onClick={handleReset}
                  style={{ fontSize: 12, padding: '4px 10px' }}
                >
                  重新导入
                </button>
              </div>

              {/* 失败明细表格 */}
              {result.errors && result.errors.length > 0 && (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8, color: 'var(--color-heading)' }}>
                    失败明细（{result.errors.length} 条）
                  </div>
                  <div style={{ maxHeight: 280, overflowY: 'auto', border: '1px solid var(--color-border)', borderRadius: 6 }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: 'var(--color-bg)', position: 'sticky', top: 0 }}>
                          <th style={thStyle}>行号</th>
                          <th style={thStyle}>资产编号</th>
                          <th style={{ ...thStyle, textAlign: 'left' }}>失败原因</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.errors.map((err, idx) => (
                          <tr
                            key={idx}
                            style={{ borderTop: '1px solid var(--color-border)', background: idx % 2 === 0 ? '#fff' : 'var(--color-bg)' }}
                          >
                            <td style={tdCenterStyle}>{err.row_number}</td>
                            <td style={tdCenterStyle}>
                              {err.asset_tag ? (
                                <span className="font-data">{err.asset_tag}</span>
                              ) : (
                                <span style={{ color: 'var(--color-muted)' }}>—</span>
                              )}
                            </td>
                            <td style={{ ...tdStyle, color: 'var(--color-danger-text)' }}>{err.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* 底部按钮 */}
        {!result && (
          <div className="modal-footer">
            <button className="btn btn-secondary" onClick={onClose} disabled={importing}>
              取消
            </button>
            <button
              className="btn btn-primary"
              onClick={handleImport}
              disabled={!file || importing}
            >
              {importing ? (
                <>
                  <span
                    style={{
                      display: 'inline-block',
                      width: 14,
                      height: 14,
                      border: '2px solid rgba(255,255,255,0.4)',
                      borderTopColor: '#fff',
                      borderRadius: '50%',
                      animation: 'spin 0.7s linear infinite',
                    }}
                  />
                  导入中...
                </>
              ) : (
                <>
                  <Upload size={14} />
                  开始导入
                </>
              )}
            </button>
          </div>
        )}
        {result && (
          <div className="modal-footer">
            <button className="btn btn-primary" onClick={onClose}>
              关闭
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// 表格样式常量
const thStyle = {
  padding: '8px 12px',
  fontWeight: 600,
  color: 'var(--color-heading)',
  textAlign: 'center',
  borderBottom: '1px solid var(--color-border)',
  whiteSpace: 'nowrap',
}

const tdStyle = {
  padding: '7px 12px',
  verticalAlign: 'top',
}

const tdCenterStyle = {
  ...tdStyle,
  textAlign: 'center',
  whiteSpace: 'nowrap',
}

export default ImportModal
