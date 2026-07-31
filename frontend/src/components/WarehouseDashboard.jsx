import { useState, useEffect } from 'react'
import axios from 'axios'
import { Package, CheckCircle } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

function WarehouseDashboard({ onAssetClick }) {
  const [stats, setStats] = useState(null)
  const [lowStockAssets, setLowStockAssets] = useState([])
  const [idleAssets, setIdleAssets] = useState([])
  const [recentAssets, setRecentAssets] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchStats()
    fetchLowStockAssets()
    fetchIdleAssets()
    fetchRecentAssets()
  }, [])

  const fetchStats = async () => {
    try {
      const response = await axios.get(`${API_URL}/warehouse/stats`)
      console.log('Warehouse stats:', response.data)
      setStats(response.data)
    } catch (error) {
      console.error('获取统计数据失败:', error)
    }
  }

  const fetchLowStockAssets = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_URL}/warehouse/?low_stock=true`)
      setLowStockAssets(response.data)
    } catch (error) {
      console.error('获取库存不足资产失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchIdleAssets = async () => {
    try {
      const response = await axios.get(`${API_URL}/assets/?status=闲置`)
      setIdleAssets(response.data)
    } catch (error) {
      console.error('获取闲置资产失败:', error)
    }
  }

  const fetchRecentAssets = async () => {
    try {
      // 获取最近3个月入库的资产（后端按 created_at 倒序返回）
      const threeMonthsAgo = new Date()
      threeMonthsAgo.setMonth(threeMonthsAgo.getMonth() - 3)
      const response = await axios.get(`${API_URL}/warehouse/`, {
        params: { since: threeMonthsAgo.toISOString().split('T')[0] }
      })
      setRecentAssets(response.data)
    } catch (error) {
      console.error('获取近期入库资产失败:', error)
    }
  }

  // 计算闲置资产品类分布数据
  const idleCategoryData = (() => {
    const categoryCount = {}
    idleAssets.forEach(asset => {
      categoryCount[asset.category] = (categoryCount[asset.category] || 0) + 1
    })
    const colors = ['#184e77', '#1e6091', '#1a759f', '#168aad', '#34a0a4', '#52b69a', '#76c893', '#99d98c', '#b5e48c', '#d9ed92']
    return Object.entries(categoryCount).map(([label, value], index) => ({
      label,
      value,
      color: colors[index % colors.length]
    })).filter(item => item.value > 0)
  })()

  const categoryColors = {
    '台式机': '#184e77',
    '笔记本电脑': '#1e6091',
    '显示器': '#1a759f',
    '鼠标键盘': '#168aad',
    '内存条': '#34a0a4',
    '硬盘': '#52b69a',
    '其他配件': '#76c893'
  }

  if (loading) {
    return <div className="loading">加载中...</div>
  }

  return (
    <div className="warehouse-dashboard">
      <div className="dashboard-header">
        <div>
          <h2>库房管理看板</h2>
          <p style={{ color: '#8E9EA4' }}>库存监控和采购建议</p>
        </div>
      </div>

      {/* 统计卡片 */}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card" style={{ borderLeft: '4px solid #375B81' }}>
            <div className="stat-value">{stats.total_items}</div>
            <div className="stat-label">资产种类</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '4px solid #E05252' }}>
            <div className="stat-value">{stats.low_stock_items}</div>
            <div className="stat-label">库存不足</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '4px solid #3A9E75' }}>
            <div className="stat-value">
              {stats.category_stats.reduce((sum, cat) => sum + cat.available_quantity, 0)}
            </div>
            <div className="stat-label">可用库存</div>
          </div>
          <div className="stat-card" style={{ borderLeft: '4px solid #D4952B' }}>
            <div className="stat-value">
              {stats.category_stats.reduce((sum, cat) => sum + cat.total_quantity, 0)}
            </div>
            <div className="stat-label">总库存</div>
          </div>
        </div>
      )}

      {/* 图表区域 */}
      <div className="warehouse-charts-section">
        <div className="warehouse-pie-chart">
          <h3>库房闲置资产品类</h3>
          {idleCategoryData.length > 0 ? (
            <div style={{ padding: '10px 0' }}>
              {idleCategoryData.map((cat, index) => (
                <CategoryBar 
                  key={cat.label}
                  label={cat.label}
                  available={cat.value}
                  total={idleAssets.length}
                  color={cat.color}
                />
              ))}
            </div>
          ) : (
            <div style={{ textAlign: 'center', color: '#999', padding: '40px' }}>暂无闲置资产</div>
          )}
        </div>
        <div className="warehouse-pie-chart">
          <h3>闲置资产品类分布</h3>
          <PieChart 
            data={idleCategoryData} 
            total={idleAssets.length} 
          />
        </div>
      </div>

      {/* 按分类展示库存 */}
      {stats && (
        <div className="category-sections">
          {stats.category_stats.map(category => (
            <div key={category.category} className="category-section">
              <div className="category-header">
                <h3>{category.category}</h3>
                <div className="category-stats">
                  <span>总数: {category.total_quantity}</span>
                  <span>可用: {category.available_quantity}</span>
                  <span className={category.available_quantity <= category.total_quantity * 0.3 ? 'low-stock' : ''}>
                    利用率: {((category.total_quantity - category.available_quantity) / category.total_quantity * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
              <CategoryBar 
                label={category.category}
                available={category.available_quantity}
                total={category.total_quantity}
                color={categoryColors[category.category] || '#8E9EA4'}
              />
            </div>
          ))}
        </div>
      )}

      <div className="charts-grid">
        {/* 近期入库资产 */}
        <div className="chart-card">
          <h3>近期入库资产 (最近3个月)</h3>
          {recentAssets.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#999', padding: '40px' }}>
              <div style={{ marginBottom: '10px' }}><Package size={48} color="#999" /></div>
              <div>最近3个月暂无入库资产</div>
            </div>
          ) : (
            <div className="recent-assets-list">
              {recentAssets.slice(0, 8).map(asset => (
                <div 
                  key={asset.id} 
                  className="recent-asset-item clickable"
                  onClick={() => onAssetClick && onAssetClick(asset)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="recent-asset-info">
                    <div className="recent-asset-name">{asset.name}</div>
                    <div className="recent-asset-category">{asset.category}</div>
                    <div className="recent-asset-date">
                      {new Date(asset.created_at).toLocaleDateString('zh-CN')} 入库
                    </div>
                  </div>
                  <div className="recent-asset-quantity">
                    <span className="quantity-badge">{asset.total_quantity}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 库存不足预警 */}
        <div className="chart-card">
          <h3>库存不足预警 ({lowStockAssets.length})</h3>
          {lowStockAssets.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#3A9E75' }}>
              <div style={{ marginBottom: '10px' }}><CheckCircle size={48} color="#3A9E75" /></div>
              <div>所有资产库存充足</div>
            </div>
          ) : (
            <div className="low-stock-list">
              {lowStockAssets.slice(0, 10).map(asset => (
                <div 
                  key={asset.id} 
                  className="low-stock-item clickable"
                  onClick={() => onAssetClick && onAssetClick(asset)}
                  style={{ cursor: 'pointer' }}
                >
                  <div className="low-stock-info">
                    <div className="low-stock-name">{asset.name}</div>
                    <div className="low-stock-category">{asset.category}</div>
                  </div>
                  <div className="low-stock-quantity">
                    <span className="current-stock">{asset.available_quantity}</span>
                    <span className="min-stock">/ {asset.minimum_stock}</span>
                  </div>
                  <div className="urgency-badge">
                    {asset.available_quantity === 0 ? '缺货' : '不足'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 采购建议 */}
        <div className="chart-card">
          <h3>采购建议</h3>
          {lowStockAssets.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#8E9EA4' }}>
              暂无需要采购的资产
            </div>
          ) : (
            <div className="purchase-suggestions">
              {lowStockAssets.slice(0, 5).map(asset => {
                const suggestedQuantity = Math.max(
                  asset.minimum_stock * 2 - asset.available_quantity,
                  asset.minimum_stock
                )
                return (
                  <div 
                    key={asset.id} 
                    className="purchase-item clickable"
                    onClick={() => onAssetClick && onAssetClick(asset)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="purchase-info">
                      <div className="purchase-name">{asset.name}</div>
                      <div className="purchase-specs">{asset.specifications || asset.model}</div>
                    </div>
                    <div className="purchase-suggestion">
                      <div className="suggested-quantity">建议采购: {suggestedQuantity} 个</div>
                      <div className="purchase-reason">
                        {asset.available_quantity === 0 ? '已缺货' : `仅剩 ${asset.available_quantity} 个`}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function CategoryBar({ label, available, total, color }) {
  const percentage = total > 0 ? (available / total) * 100 : 0
  
  return (
    <div style={{ marginBottom: '12px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontSize: '13px', color: '#4A5568' }}>{label}</span>
        <span style={{ 
          fontSize: '13px', 
          fontWeight: 'bold', 
          color: '#1F3247' 
        }}>
          {available} 件 ({percentage.toFixed(1)}%)
        </span>
      </div>
      <div style={{ 
        width: '100%', 
        height: '8px', 
        background: '#e0e0e0', 
        borderRadius: '4px',
        overflow: 'hidden'
      }}>
        <div style={{ 
          width: `${percentage}%`, 
          height: '100%', 
          background: color,
          transition: 'width 0.3s ease'
        }} />
      </div>
    </div>
  )
}

function PieChart({ data, total }) {
  if (data.length === 0 || total === 0) {
    return <div style={{ textAlign: 'center', color: '#999', padding: '40px' }}>暂无数据</div>
  }
  const size = 160
  const strokeWidth = 30
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const centerX = size / 2
  const centerY = size / 2
  let currentAngle = -90

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '20px', flexWrap: 'wrap', padding: '10px 0' }}>
      <svg viewBox={`0 0 ${size} ${size}`} style={{ width: '100%', maxWidth: '150px', height: 'auto', flexShrink: 0 }}>
        {data.map((item, index) => {
          const percentage = item.value / total
          const strokeDasharray = `${circumference * percentage} ${circumference * (1 - percentage)}`
          const rotation = currentAngle
          currentAngle += percentage * 360
          return (
            <circle key={index} cx={centerX} cy={centerY} r={radius} fill="none" stroke={item.color} strokeWidth={strokeWidth} strokeDasharray={strokeDasharray} transform={`rotate(${rotation} ${centerX} ${centerY})`} />
          )
        })}
        <text x={centerX} y={centerY - 5} textAnchor="middle" fontSize="20" fontWeight="bold" fill="#1F3247">{total}</text>
        <text x={centerX} y={centerY + 12} textAnchor="middle" fontSize="11" fill="#8E9EA4">总计</text>
      </svg>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {data.map((item, index) => (
          <div key={index} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
            <div style={{ width: '10px', height: '10px', borderRadius: '2px', backgroundColor: item.color }} />
            <span style={{ color: '#4A5568' }}>{item.label}</span>
            <span style={{ fontWeight: 'bold', color: '#1F3247' }}>{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default WarehouseDashboard