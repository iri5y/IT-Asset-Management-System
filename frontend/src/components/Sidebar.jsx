import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'
import {useAuth} from '../contexts/AuthContext'
import { Upload, Download, CheckSquare, Square, SlidersHorizontal, X } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

const PAGE_SIZE = 50

// ── CSV 导出工具函数 ──────────────────────────────────────────
function exportLabelCsv(assets) {
  const COLUMNS = [
    { header: '资产编号 (Asset Tag)', key: 'asset_tag' },
    { header: '序列号 (Serial No.)',   key: 'serial_number' },
    { header: '资产名 (hostname)',     key: 'hostname' },
    { header: '型号 (Model)',          key: 'model' },
  ]
  const escapeCell = (val) => {
    if (val === null || val === undefined) return ''
    const str = String(val)
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`
    }
    return str
  }
  const headerRow = COLUMNS.map(c => escapeCell(c.header)).join(',')
  const dataRows = assets.map(asset => COLUMNS.map(c => escapeCell(asset[c.key])).join(','))
  const csvContent = '\uFEFF' + [headerRow, ...dataRows].join('\r\n')
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const now = new Date()
  const dateStr = `${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}`
  const link = document.createElement('a')
  link.href = url
  link.setAttribute('download', `资产标签_${dateStr}.csv`)
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
// ─────────────────────────────────────────────────────────────

const EMPTY_FILTERS = {
  search: '',
  category: '',
  status: '',
  department: '',
  po_number: '',
  location: '',
}

function Sidebar({ assets, selectedAsset, onSelectAsset, filters, setFilters, onImport }) {
  const {isReadonly} = useAuth()
  const [departments, setDepartments] = useState([])
  const [officeLocations, setOfficeLocations] = useState([])
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [checkedIds, setCheckedIds] = useState(new Set())
  // 筛选面板展开/收起
  const [filterOpen, setFilterOpen] = useState(false)
  const listRef = useRef(null)

  useEffect(() => {
    axios.get(`${API_URL}/departments/flat`).then(res => setDepartments(res.data)).catch(() => {})
    axios.get(`${API_URL}/office-locations/`).then(res => setOfficeLocations(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    setVisibleCount(PAGE_SIZE)
    setCheckedIds(new Set())
  }, [filters, assets.length])

  const handleChange = (e) => {
    setFilters({ ...filters, [e.target.name]: e.target.value })
  }

  // 计算已激活的筛选条件数量（不含搜索框）
  const activeFilterCount = ['category', 'status', 'department', 'po_number', 'location']
    .filter(k => filters[k] && filters[k] !== '').length

  const handleClearFilters = () => {
    setFilters(EMPTY_FILTERS)
  }

  const handleScroll = useCallback(() => {
    const el = listRef.current
    if (!el) return
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 200) {
      setVisibleCount(prev => Math.min(prev + PAGE_SIZE, assets.length))
    }
  }, [assets.length])

  const handleCheck = (e, assetId) => {
    e.stopPropagation()
    setCheckedIds(prev => {
      const next = new Set(prev)
      next.has(assetId) ? next.delete(assetId) : next.add(assetId)
      return next
    })
  }

  const handleToggleAll = () => {
    const visibleIds = assets.slice(0, visibleCount).map(a => a.id)
    const allChecked = visibleIds.every(id => checkedIds.has(id))
    if (allChecked) {
      setCheckedIds(new Set())
    } else {
      setCheckedIds(new Set(visibleIds))
    }
  }

  const handleExport = () => {
    const selected = assets.filter(a => checkedIds.has(a.id))
    if (selected.length === 0) return
    exportLabelCsv(selected)
  }

  const visibleAssets = assets.slice(0, visibleCount)
  const hasMore = visibleCount < assets.length
  const visibleIds = visibleAssets.map(a => a.id)
  const allVisibleChecked = visibleIds.length > 0 && visibleIds.every(id => checkedIds.has(id))
  const someChecked = checkedIds.size > 0

  return (
    <div className="sidebar">
      <div className="sidebar-header">

        {/* 顶部：资产数量 + 批量导入 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 13, color: '#8E9EA4' }}>共 {assets.length} 个资产</span>
          <div style={{ display: 'flex', gap: 6 }}>
            {onImport && !isReadonly &&(
              <button
                className="btn btn-primary"
                onClick={onImport}
                style={{ fontSize: 12, padding: '4px 10px', gap: 4 }}
                title="批量导入资产"
              >
                <Upload size={13} />
                批量导入
              </button>
            )}
          </div>
        </div>

        {/* 勾选操作栏 */}
        {someChecked ? (
          <div className="label-export-bar">
            <button className="label-export-select-all" onClick={handleToggleAll}>
              {allVisibleChecked ? <CheckSquare size={14} /> : <Square size={14} />}
              {allVisibleChecked ? '取消全选' : '全选当前页'}
            </button>
            <span className="label-export-count">已选 {checkedIds.size} 个</span>
            <button className="btn btn-export" onClick={handleExport}>
              <Download size={13} />
              导出标签
            </button>
          </div>
        ) : (
          <button className="label-export-hint" onClick={handleToggleAll} title="勾选资产后可导出标签 CSV">
            <Square size={13} />
            勾选导出标签
          </button>
        )}

        {/* 搜索框 + 筛选按钮 */}
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 8 }}>
          <input
            type="text"
            name="search"
            className="sidebar-search"
            placeholder="搜索资产..."
            value={filters.search}
            onChange={handleChange}
            style={{ flex: 1, margin: 0 }}
          />
          <button
            onClick={() => setFilterOpen(v => !v)}
            title="筛选条件"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              padding: '7px 10px',
              borderRadius: 'var(--radius)',
              border: `1.5px solid ${filterOpen || activeFilterCount > 0 ? 'var(--color-primary)' : 'var(--color-border)'}`,
              background: filterOpen || activeFilterCount > 0 ? 'var(--color-primary-light, #EBF0F8)' : '#fff',
              color: filterOpen || activeFilterCount > 0 ? 'var(--color-primary)' : 'var(--color-muted)',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 500,
              whiteSpace: 'nowrap',
              flexShrink: 0,
            }}
          >
            <SlidersHorizontal size={14} />
            筛选
            {activeFilterCount > 0 && (
              <span style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                width: 16, height: 16, borderRadius: '50%',
                background: 'var(--color-primary)', color: '#fff',
                fontSize: 10, fontWeight: 700, marginLeft: 2,
              }}>
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {/* 已激活的筛选标签（快速预览 + 单独清除） */}
        {activeFilterCount > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
            {[
              { key: 'category', label: '品类' },
              { key: 'status',   label: '状态' },
              { key: 'department', label: '部门' },
              { key: 'po_number',  label: 'PO号' },
              { key: 'location',   label: '位置' },
            ].filter(f => filters[f.key]).map(f => (
              <span
                key={f.key}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 3,
                  padding: '2px 8px', borderRadius: 12,
                  background: 'var(--color-primary-light, #EBF0F8)',
                  color: 'var(--color-primary)',
                  fontSize: 11, fontWeight: 500,
                  border: '1px solid var(--color-primary)',
                }}
              >
                {f.label}: {filters[f.key]}
                <X
                  size={10}
                  style={{ cursor: 'pointer', marginLeft: 1 }}
                  onClick={() => setFilters({ ...filters, [f.key]: '' })}
                />
              </span>
            ))}
            <span
              style={{ fontSize: 11, color: 'var(--color-muted)', cursor: 'pointer', alignSelf: 'center', marginLeft: 2 }}
              onClick={handleClearFilters}
            >
              清除全部
            </span>
          </div>
        )}

        {/* 可折叠筛选面板 */}
        {filterOpen && (
          <div style={{
            marginTop: 10,
            padding: '12px 14px',
            background: 'var(--color-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)',
            display: 'flex',
            flexDirection: 'column',
            gap: 10,
          }}>
            {/* 标题行 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-heading)' }}>筛选条件</span>
              {activeFilterCount > 0 && (
                <button
                  onClick={handleClearFilters}
                  style={{ fontSize: 11, color: 'var(--color-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                >
                  清除全部
                </button>
              )}
            </div>

            {/* 品类 */}
            <div>
              <div style={labelStyle}>品类</div>
              <select name="category" value={filters.category} onChange={handleChange} style={selectStyle}>
                <option value="">全部品类</option>
                <option value="台式机">台式机</option>
                <option value="笔记本电脑">笔记本电脑</option>
                <option value="平板电脑">平板电脑</option>
              </select>
            </div>

            {/* 状态 */}
            <div>
              <div style={labelStyle}>状态</div>
              <select name="status" value={filters.status} onChange={handleChange} style={selectStyle}>
                <option value="">全部状态</option>
                <option value="使用中">使用中</option>
                <option value="维修中">维修中</option>
                <option value="闲置">闲置</option>
                <option value="报废">报废</option>
              </select>
            </div>

            {/* 部门 */}
            <div>
              <div style={labelStyle}>部门</div>
              <select name="department" value={filters.department || ''} onChange={handleChange} style={selectStyle}>
                <option value="">全部部门</option>
                {departments.map(d => (
                  <option key={d.id} value={d.display}>{d.display}</option>
                ))}
              </select>
            </div>

            {/* 资产位置 */}
            <div>
              <div style={labelStyle}>资产位置</div>
              <select name="location" value={filters.location || ''} onChange={handleChange} style={selectStyle}>
                <option value="">全部位置</option>
                {officeLocations.map(loc => (
                  <option key={loc.id} value={loc.name}>{loc.name}</option>
                ))}
              </select>
            </div>

            {/* PO号 */}
            <div>
              <div style={labelStyle}>PO号</div>
              <input
                type="text"
                name="po_number"
                value={filters.po_number || ''}
                onChange={handleChange}
                placeholder="输入PO号搜索..."
                style={{
                  width: '100%',
                  padding: '6px 10px',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius)',
                  fontSize: 13,
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </div>
        )}
      </div>

      {/* 资产列表 */}
      <div className="asset-list" ref={listRef} onScroll={handleScroll}>
        {assets.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#999' }}>
            没有找到资产
          </div>
        ) : (
          <>
            {visibleAssets.map(asset => (
              <div
                key={asset.id}
                className={`asset-item ${selectedAsset?.id === asset.id ? 'active' : ''} ${checkedIds.has(asset.id) ? 'checked' : ''} ${asset.status === '报废' ? 'retired' : ''}`}
                onClick={() => onSelectAsset(asset)}
              >
                <input
                  type="checkbox"
                  className="asset-item-checkbox"
                  checked={checkedIds.has(asset.id)}
                  onChange={(e) => handleCheck(e, asset.id)}
                  onClick={(e) => e.stopPropagation()}
                  title="勾选以导出标签"
                />
                <div className="asset-item-body">
                  <div className="asset-item-header">
                    <span className="asset-item-tag">
                      {asset.hostname || asset.asset_tag}
                    </span>
                    <span className={`status-badge status-${asset.status.replace(/\s+/g, '-')}`}>
                      {asset.status}
                    </span>
                  </div>
                  <div className="asset-item-info">
                    <div><strong>品类:</strong> {asset.category}</div>
                    {asset.brand && <div><strong>品牌:</strong> {asset.brand}</div>}
                    {asset.model && <div><strong>型号:</strong> {asset.model}</div>}
                    {asset.employee_name && <div><strong>使用人:</strong> {asset.employee_name}</div>}
                    {asset.department && <div><strong>部门:</strong> {asset.department}</div>}
                  </div>
                </div>
              </div>
            ))}
            {hasMore && (
              <div style={{ padding: '12px', textAlign: 'center', color: '#8E9EA4', fontSize: '13px' }}>
                已显示 {visibleCount} / {assets.length} 条，向下滚动加载更多
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// 筛选面板内部样式常量
const labelStyle = {
  fontSize: 11,
  fontWeight: 600,
  color: 'var(--color-muted)',
  marginBottom: 4,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
}

const selectStyle = {
  width: '100%',
  padding: '6px 10px',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius)',
  fontSize: 13,
  background: '#fff',
  boxSizing: 'border-box',
}

export default Sidebar
