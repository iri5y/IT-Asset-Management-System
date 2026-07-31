import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import { Archive } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const PAGE_SIZE = 50

function RetiredAssets({ onAssetSelect }) {
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({ search: '', category: '' })
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const listRef = useRef(null)

  useEffect(() => {
    fetchRetiredAssets()
  }, [filters])

  useEffect(() => {
    setVisibleCount(PAGE_SIZE)
  }, [filters, assets.length])

  const fetchRetiredAssets = async () => {
    try {
      setLoading(true)
      const params = { status: '报废' }
      if (filters.search) params.search = filters.search
      if (filters.category) params.category = filters.category
      const res = await axios.get(`${API_URL}/assets/`, { params })
      setAssets(res.data)
    } catch (err) {
      console.error('获取报废资产失败:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleFilterChange = (e) => {
    setFilters(prev => ({ ...prev, [e.target.name]: e.target.value }))
  }

  const handleScroll = useCallback(() => {
    const el = listRef.current
    if (!el) return
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 200) {
      setVisibleCount(prev => Math.min(prev + PAGE_SIZE, assets.length))
    }
  }, [assets.length])

  const formatDate = (dateStr) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString('zh-CN')
  }

  const visibleAssets = assets.slice(0, visibleCount)
  const hasMore = visibleCount < assets.length

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto' }}>
      {/* 页头 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 20, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
            <Archive size={20} style={{ color: 'var(--color-muted)' }} />
            报废资产
          </h2>
          <p style={{ color: 'var(--color-muted)', fontSize: 13 }}>
            共 {assets.length} 个已报废资产
          </p>
        </div>
      </div>

      {/* 筛选栏 */}
      <div style={{
        display: 'flex', gap: 12, marginBottom: 20,
        padding: '12px 16px', background: 'var(--color-surface)',
        border: '1px solid var(--color-border)', borderRadius: 'var(--radius)',
      }}>
        <input
          type="text"
          name="search"
          value={filters.search}
          onChange={handleFilterChange}
          placeholder="搜索资产编号、资产名、型号、序列号..."
          style={{
            flex: 1, padding: '8px 12px',
            border: '1px solid var(--color-border)', borderRadius: 'var(--radius)',
            fontSize: 13, background: 'var(--color-bg)',
          }}
        />
        <select
          name="category"
          value={filters.category}
          onChange={handleFilterChange}
          style={{
            padding: '8px 12px', border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)', fontSize: 13, background: 'var(--color-surface)',
            minWidth: 130,
          }}
        >
          <option value="">全部品类</option>
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

      {/* 列表 */}
      {loading ? (
        <div className="loading">加载中...</div>
      ) : assets.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><Archive size={48} /></div>
          <h3>暂无报废资产</h3>
          <p>所有资产均处于正常使用状态</p>
        </div>
      ) : (
        <div
          ref={listRef}
          onScroll={handleScroll}
          style={{ maxHeight: 'calc(100vh - 320px)', overflowY: 'auto' }}
        >
          {/* 表头 */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 80px 90px 120px 120px 140px',
            gap: 12,
            padding: '8px 16px',
            background: 'var(--color-bg)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius)',
            marginBottom: 6,
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--color-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
          }}>
            <span>资产信息</span>
            <span>品类</span>
            <span>序列号</span>
            <span>原使用人</span>
            <span>原部门</span>
            <span>报废备注</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {visibleAssets.map(asset => (
              <div
                key={asset.id}
                onClick={() => onAssetSelect && onAssetSelect(asset)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 80px 90px 120px 120px 140px',
                  gap: 12,
                  padding: '12px 16px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius)',
                  cursor: onAssetSelect ? 'pointer' : 'default',
                  transition: 'border-color 0.15s',
                  alignItems: 'center',
                }}
                onMouseEnter={e => { if (onAssetSelect) e.currentTarget.style.borderColor = 'var(--color-primary)' }}
                onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--color-border)'}
              >
                {/* 资产信息 */}
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--color-heading)', marginBottom: 2 }}>
                    {asset.hostname || asset.asset_tag}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--color-muted)' }}>
                    {asset.asset_tag}
                    {asset.brand && ` · ${asset.brand}`}
                    {asset.model && ` ${asset.model}`}
                  </div>
                </div>

                {/* 品类 */}
                <div style={{ fontSize: 12, color: 'var(--color-body)' }}>{asset.category}</div>

                {/* 序列号 */}
                <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--color-muted)' }}>
                  {asset.serial_number || '-'}
                </div>

                {/* 原使用人 */}
                <div style={{ fontSize: 12, color: 'var(--color-body)' }}>
                  {asset.employee_name || '-'}
                </div>

                {/* 原部门 */}
                <div style={{ fontSize: 12, color: 'var(--color-body)' }}>
                  {asset.department || '-'}
                </div>

                {/* 报废备注 */}
                <div style={{
                  fontSize: 11, color: 'var(--color-muted)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }} title={asset.notes || ''}>
                  {asset.notes || '-'}
                </div>
              </div>
            ))}
          </div>

          {hasMore && (
            <div style={{ padding: '12px', textAlign: 'center', color: 'var(--color-muted)', fontSize: 13 }}>
              已显示 {visibleCount} / {assets.length} 条，向下滚动加载更多
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default RetiredAssets
