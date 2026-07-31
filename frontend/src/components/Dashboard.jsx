import { useMemo, useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import axios from 'axios'
import { Search, Monitor, Laptop, Tablet, Mouse, Phone, BarChart3, ClipboardCopy } from 'lucide-react'

function Dashboard({ assets, onGlobalSearch }) {
  const navigate = useNavigate()
  
  const stats = useMemo(() => {
    const total = assets.length
    const assigned = assets.filter(a => a.status === '使用中' && a.employee_name && a.employee_name.trim() !== '').length
    const inStorage = assets.filter(a => a.status === '闲置').length
    const active = assets.filter(a => a.status === '使用中').length
    const inRepair = assets.filter(a => a.status === '维修中').length
    const retired = assets.filter(a => a.status === '报废').length
    
    const categoryCount = {}
    const brandCount = {}
    const departmentCount = {}
    
    assets.forEach(asset => {
      categoryCount[asset.category] = (categoryCount[asset.category] || 0) + 1
      if (asset.brand) {
        brandCount[asset.brand] = (brandCount[asset.brand] || 0) + 1
      }
      if (asset.department) {
        departmentCount[asset.department] = (departmentCount[asset.department] || 0) + 1
      }
    })
    
    return { total, assigned, inStorage, active, inRepair, retired, categoryCount, brandCount, departmentCount }
  }, [assets])

  const statusData = [
    { label: '使用中', value: stats.active, color: '#184e77' },
    { label: '闲置', value: stats.inStorage, color: '#34a0a4' },
    { label: '维修中', value: stats.inRepair, color: '#76c893' },
    { label: '报废', value: stats.retired, color: '#b5e48c' }
  ].filter(item => item.value > 0)

  const categoryData = Object.entries(stats.categoryCount).map(([label, value], index) => {
    const colors = ['#184e77', '#1e6091', '#1a759f', '#168aad', '#34a0a4', '#52b69a', '#76c893', '#99d98c', '#b5e48c', '#d9ed92']
    return { label, value, color: colors[index % colors.length] }
  }).filter(item => item.value > 0)

  const handleStatClick = (type) => {
    switch(type) {
      case 'total':
        navigate('/assets?clear=true')
        break
      case 'assigned':
        navigate('/assets?status=使用中')
        break
      case 'storage':
        navigate('/warehouse/idle')
        break
      case 'repair':
        navigate('/assets?status=维修中')
        break
      default:
        break
    }
  }

  const [searchTerm, setSearchTerm] = useState('')
  const [searchFocused, setSearchFocused] = useState(false)
  const searchRef = useRef(null)

  // 点击外部关闭下拉
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setSearchFocused(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const searchResults = useMemo(() => {
    if (!searchTerm.trim() || searchTerm.trim().length < 1) return []
    const term = searchTerm.toLowerCase()
    return assets.filter(a =>
      (a.asset_tag && a.asset_tag.toLowerCase().includes(term)) ||
      (a.hostname && a.hostname.toLowerCase().includes(term)) ||
      (a.brand && a.brand.toLowerCase().includes(term)) ||
      (a.model && a.model.toLowerCase().includes(term)) ||
      (a.employee_name && a.employee_name.toLowerCase().includes(term)) ||
      (a.employee_id && a.employee_id.toLowerCase().includes(term)) ||
      (a.serial_number && a.serial_number.toLowerCase().includes(term)) ||
      (a.po_number && a.po_number.toLowerCase().includes(term)) ||
      (a.category && a.category.toLowerCase().includes(term))
    ).slice(0, 8)
  }, [searchTerm, assets])

  const handleSearchSelect = (asset) => {
    setSearchTerm('')
    setSearchFocused(false)
    // 跳转到资产管理页面并选中该资产
    navigate('/assets')
    setTimeout(() => {
      window.dispatchEvent(new CustomEvent('selectAsset', { detail: { assetId: asset.id } }))
    }, 300)
  }

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <div className="dashboard-title-section">
          <h2>资产管理看板</h2>
          <p style={{ color: '#8E9EA4' }}>实时统计和数据分析</p>
        </div>
      </div>

      <div className="dashboard-search-bar" ref={searchRef}>
        <Search size={20} style={{ position: 'absolute', left: '16px', top: '14px', color: '#8E9EA4', pointerEvents: 'none', zIndex: 1 }} />
        <input
          type="text"
          className="global-search-input"
          placeholder="搜索资产编号、资产名、品牌、型号、使用人..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          onFocus={() => setSearchFocused(true)}
        />
        {searchFocused && searchTerm.trim() && (
          <div className="search-dropdown">
            {searchResults.length === 0 ? (
              <div className="search-dropdown-empty">未找到匹配的资产</div>
            ) : (
              searchResults.map(asset => (
                <div key={asset.id} className="search-dropdown-item" onClick={() => handleSearchSelect(asset)}>
                  <div className="search-item-main">
                    <span className="search-item-tag font-data">{asset.hostname || asset.asset_tag}</span>
                    <span className={`status-badge status-${asset.status.replace(/\s+/g, '-')}`}>{asset.status}</span>
                  </div>
                  <div className="search-item-sub">
                    {asset.category}{asset.brand ? ` · ${asset.brand}` : ''}{asset.model ? ` ${asset.model}` : ''}{asset.employee_name ? ` · ${asset.employee_name}` : ''}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      <div className="dashboard-layout">
        {/* 左侧：统计卡片和周报 */}
        <div className="dashboard-left">
          <div className="stats-grid clickable-stats">
            <div className="stat-card clickable" onClick={() => handleStatClick('total')}>
              <div className="stat-value">{stats.total}</div>
              <div className="stat-label">总资产数</div>
            </div>
            <div className="stat-card clickable" style={{ borderLeftColor: '#375B81' }} onClick={() => handleStatClick('assigned')}>
              <div className="stat-value">{stats.assigned}</div>
              <div className="stat-label">已分配</div>
            </div>
            <div className="stat-card clickable" style={{ borderLeftColor: '#375B81' }} onClick={() => handleStatClick('storage')}>
              <div className="stat-value">{stats.inStorage}</div>
              <div className="stat-label">库存</div>
            </div>
            <div className="stat-card clickable" style={{ borderLeftColor: '#8E9EA4' }} onClick={() => handleStatClick('repair')}>
              <div className="stat-value">{stats.inRepair}</div>
              <div className="stat-label">维修中</div>
            </div>
          </div>

          <WeeklyReportSummary />
        </div>

        {/* 右侧：图表 */}
        <div className="dashboard-charts">
          <div className="chart-card">
            <h3>资产状态分布</h3>
            <PieChart data={statusData} total={stats.total} />
          </div>
          <div className="chart-card">
            <h3>品类分布</h3>
            <PieChart data={categoryData} total={stats.total} />
          </div>
          <div className="chart-card">
            <h3>品牌分布 (Top 10)</h3>
            <div style={{ padding: '10px 0' }}>
              {Object.entries(stats.brandCount).sort((a, b) => b[1] - a[1]).slice(0, 10).map(([brand, count]) => (
                <StatusBar key={brand} label={brand} value={count} total={stats.total} color="#1a759f" />
              ))}
            </div>
          </div>
          <div className="chart-card">
            <h3>部门分布 (Top 15) </h3>
            <div style={{ padding: '10px 0' }}>
              {Object.entries(stats.departmentCount).sort((a, b) => b[1] - a[1]).slice(0, 15).map(([department, count]) => (
                <StatusBar key={department} label={department} value={count} total={stats.total} color="#168aad" />
              ))}
              {Object.keys(stats.departmentCount).length === 0 && (
                <div style={{ textAlign: 'center', color: '#999', padding: '20px' }}>暂无部门数据</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function PieChart({ data, total }) {
  if (data.length === 0 || total === 0) {
    return <div style={{ textAlign: 'center', color: '#999', padding: '40px' }}>暂无数据</div>
  }
  const size = 200
  const strokeWidth = 35
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const centerX = size / 2
  const centerY = size / 2
  let currentAngle = -90

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '20px', flexWrap: 'wrap', padding: '10px 0' }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: '100%', maxWidth: '180px', height: 'auto', flexShrink: 0 }}>
        {data.map((item, index) => {
          const percentage = item.value / total
          const strokeDasharray = `${circumference * percentage} ${circumference * (1 - percentage)}`
          const rotation = currentAngle
          currentAngle += percentage * 360
          return (
            <circle key={index} cx={centerX} cy={centerY} r={radius} fill="none" stroke={item.color} strokeWidth={strokeWidth} strokeDasharray={strokeDasharray} transform={`rotate(${rotation} ${centerX} ${centerY})`} />
          )
        })}
        <text x={centerX} y={centerY - 3} textAnchor="middle" fontSize="24" fontWeight="bold" fill="#1F3247">{total}</text>
        <text x={centerX} y={centerY + 14} textAnchor="middle" fontSize="12" fill="#8E9EA4">总计</text>
      </svg>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {data.map((item, index) => (
          <div key={index} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '2px', backgroundColor: item.color, flexShrink: 0 }} />
            <span style={{ color: '#4A5568', whiteSpace: 'nowrap' }}>{item.label}</span>
            <span style={{ fontWeight: 'bold', color: '#1F3247' }}>{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function StatusBar({ label, value, total, color }) {
  const percentage = total > 0 ? (value / total) * 100 : 0
  return (
    <div style={{ marginBottom: '12px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontSize: '13px', color: '#4A5568' }}>{label}</span>
        <span style={{ fontSize: '13px', fontWeight: 'bold', color: '#1F3247' }}>{value} ({percentage.toFixed(1)}%)</span>
      </div>
      <div style={{ width: '100%', height: '6px', background: '#DDE3E9', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ width: `${percentage}%`, height: '100%', background: color }} />
      </div>
    </div>
  )
}

function WeeklyReportSummary() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    axios.get(`${API_URL}/assets/weekly-distribution`)
      .then(res => setData(res.data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const categoryIcons = {
    '台式机': <Monitor size={18} color="#fff" />,
    '笔记本电脑': <Laptop size={18} color="#fff" />,
    '移动设备': <Tablet size={18} color="#fff" />,
    '手机': <Phone size={18} color="#fff" />,
    '无线鼠标': <Mouse size={18} color="#fff" />,
  }
  const colors = ['#184e77', '#1e6091', '#1a759f', '#168aad', '#34a0a4', '#52b69a', '#76c893', '#99d98c', '#b5e48c', '#d9ed92']

  const copyToClipboard = () => {
    if (!data) return
    let text = `本周发放资产统计 (${data.week_start} ~ ${data.week_end})\n\n`
    data.categories.forEach(cat => {
      text += `${cat.category}: ${cat.count} 台\n`
      cat.items.forEach(item => { text += `  - ${item.name} (${item.model})\n` })
    })
    text += `\n总计发放: ${data.total} 台\n报告生成: ${new Date().toLocaleString('zh-CN')}`
    navigator.clipboard.writeText(text).then(() => alert('已复制到剪贴板！'))
  }

  if (loading) return <div className="weekly-report-section"><div className="weekly-report-card" style={{ textAlign: 'center', padding: 30, color: '#8E9EA4' }}>加载中...</div></div>

  return (
    <div className="weekly-report-section">
      <div className="weekly-report-card">
        <div className="weekly-report-header">
          <div>
            <h3><BarChart3 size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} /> 本周发放资产统计</h3>
            {data && <p className="report-period">统计周期: {data.week_start} (周五) ~ {data.week_end} (周四)</p>}
          </div>
          <button className="btn btn-copy" onClick={copyToClipboard}><ClipboardCopy size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} /> 复制</button>
        </div>

        {data && (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
              {data.categories.map((cat, i) => (
                <div key={cat.category} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '8px 10px', background: 'var(--color-bg)', borderRadius: 'var(--radius)', border: '1px solid var(--color-border)' }}>
                  <div style={{ width: 32, height: 32, borderRadius: 'var(--radius)', background: colors[i % colors.length], display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: 2 }}>
                    {categoryIcons[cat.category] || <BarChart3 size={16} color="#fff" />}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--color-heading)' }}>{cat.category}</span>
                      <span className="font-data" style={{ fontSize: 14, fontWeight: 700, color: cat.count > 0 ? colors[i % colors.length] : 'var(--color-muted)' }}>{cat.count}</span>
                    </div>
                    {cat.items.length > 0 && (
                      <div style={{ marginTop: 4 }}>
                        {cat.items.map((item, j) => (
                          <div key={j} style={{ fontSize: 11, color: 'var(--color-muted)', lineHeight: 1.6 }}>
                            {item.name} <span style={{ color: 'var(--color-body)' }}>({item.model})</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <div className="report-summary">
              <div className="summary-item">
                <span className="summary-label">本周总计发放:</span>
                <span className="summary-value font-data">{data.total} 台</span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

export default Dashboard
