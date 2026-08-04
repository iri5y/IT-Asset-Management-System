import { useState, useEffect } from 'react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''

function WarehouseSidebar({ selectedAsset, onAssetSelect }) {
  const [assets, setAssets] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    fetchAssets()
  }, [])

  const fetchAssets = async () => {
    try {
      setLoading(true)
      const response = await axios.get(`${API_URL}/warehouse/`)
      setAssets(response.data)
    } catch (error) {
      console.error('获取库房资产失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const getStockStatus = (asset) => {
    if (asset.available_quantity <= asset.minimum_stock) {
      return { color: '#EF4444', bg: '#FEF2F2', border: '#FECACA', text: '库存不足' }
    } else if (asset.available_quantity <= asset.minimum_stock * 2) {
      return { color: '#F59E0B', bg: '#FFFBEB', border: '#FDE68A', text: '库存偏低' }
    } else {
      return { color: '#10B981', bg: '#F0FDF4', border: '#A7F3D0', text: '库存充足' }
    }
  }

  const filteredAssets = assets.filter(asset => 
    asset.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    asset.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
    (asset.brand && asset.brand.toLowerCase().includes(searchTerm.toLowerCase()))
  )

  return (
    <div className="warehouse-sidebar-panel">
      <div className="warehouse-sidebar-header">
        <h3>库存资产列表</h3>
        <span className="asset-count">{assets.length} 项</span>
      </div>
      
      <div className="warehouse-sidebar-search">
        <input
          type="text"
          placeholder="搜索资产..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      <div className="warehouse-sidebar-list">
        {loading ? (
          <div className="loading">加载中...</div>
        ) : filteredAssets.length === 0 ? (
          <div className="empty-state" style={{ padding: '20px', textAlign: 'center' }}>
            <p>没有找到资产</p>
          </div>
        ) : (
          filteredAssets.map(asset => {
            const stockStatus = getStockStatus(asset)
            const isSelected = selectedAsset && selectedAsset.id === asset.id
            
            return (
              <div
                key={asset.id}
                className={`warehouse-sidebar-item ${isSelected ? 'selected' : ''}`}
                onClick={() => onAssetSelect(asset)}
              >
                <div className="item-header">
                  <span className="item-name">{asset.name}</span>
                  <span 
                    className="item-status"
                    style={{ 
                      backgroundColor: stockStatus.bg, 
                      color: stockStatus.color,
                      border: `1px solid ${stockStatus.border}`
                    }}
                  >
                    {asset.available_quantity}
                  </span>
                </div>
                <div className="item-info">
                  <span className="item-category">{asset.category}</span>
                  {asset.brand && <span className="item-brand">{asset.brand}</span>}
                  <span className="item-stock-text" style={{ color: stockStatus.color }}>
                    {stockStatus.text}
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default WarehouseSidebar
