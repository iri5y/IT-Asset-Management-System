import { useEffect, useState } from 'react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''
const EMPTY_FILTERS = {
  name: '', primary_category_id: '', secondary_category_id: '', available_quantity: '',
  allocated_quantity: '', location: '', low_stock_threshold: '', low_stock: '',
}

function WarehouseSidebar({ selectedAsset, onAssetSelect }) {
  const [assets, setAssets] = useState([])
  const [primaryCategories, setPrimaryCategories] = useState([])
  const [secondaryCategories, setSecondaryCategories] = useState([])
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadSecondaryCategories = async (primaryId) => {
    if (!primaryId) { setSecondaryCategories([]); return }
    const response = await axios.get(`${API_URL}/warehouse/categories/primary/${primaryId}/secondary`)
    setSecondaryCategories(response.data)
  }

  const loadMaterials = async () => {
    try {
      setLoading(true)
      setError('')
      const params = {}
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== '') params[key] = value
      })
      const response = await axios.get(`${API_URL}/warehouse/materials`, { params })
      setAssets(response.data)
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '获取仓储物料失败')
    } finally { setLoading(false) }
  }

  useEffect(() => {
    axios.get(`${API_URL}/warehouse/categories/primary`)
      .then(response => setPrimaryCategories(response.data))
      .catch(requestError => setError(requestError.response?.data?.detail || '获取一级分类失败'))
  }, [])
  useEffect(() => { loadMaterials() }, [filters])

  const changeFilter = async (event) => {
    const { name, value } = event.target
    if (name === 'primary_category_id') {
      setFilters(current => ({ ...current, primary_category_id: value, secondary_category_id: '' }))
      try { await loadSecondaryCategories(value) } catch (requestError) { setError(requestError.response?.data?.detail || '获取二级分类失败') }
      return
    }
    setFilters(current => ({ ...current, [name]: value }))
  }

  const resetFilters = () => {
    setSecondaryCategories([])
    setFilters(EMPTY_FILTERS)
  }

  return <div className="warehouse-sidebar-panel">
    <div className="warehouse-sidebar-header"><h3>仓储物料筛选</h3><span className="asset-count">{assets.length} 项</span></div>
    <div className="warehouse-sidebar-search" style={{ display: 'grid', gap: 8 }}>
      <input name="name" value={filters.name} onChange={changeFilter} placeholder="物料名称" />
      <select name="primary_category_id" value={filters.primary_category_id} onChange={changeFilter}>
        <option value="">所有一级分类</option>{primaryCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}
      </select>
      <select name="secondary_category_id" value={filters.secondary_category_id} disabled={!filters.primary_category_id} onChange={changeFilter}>
        <option value="">{filters.primary_category_id ? '所有二级分类' : '请先选择一级分类'}</option>{secondaryCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}
      </select>
      <input type="number" min="0" name="available_quantity" value={filters.available_quantity} onChange={changeFilter} placeholder="可用数量（精确）" />
      <input type="number" min="0" name="allocated_quantity" value={filters.allocated_quantity} onChange={changeFilter} placeholder="已分配数量（精确）" />
      <input name="location" value={filters.location} onChange={changeFilter} placeholder="存放位置" />
      <input type="number" min="0" name="low_stock_threshold" value={filters.low_stock_threshold} onChange={changeFilter} placeholder="低库存阈值（精确）" />
      <select name="low_stock" value={filters.low_stock} onChange={changeFilter}><option value="">全部库存状态</option><option value="true">仅低库存预警</option><option value="false">仅库存正常</option></select>
      <button className="btn btn-secondary" onClick={resetFilters}>重置筛选</button>
    </div>
    {error && <div className="alert alert-error">{error}</div>}
    <div className="warehouse-sidebar-list">
      {loading ? <div className="loading">加载中...</div> : assets.length === 0 ? <div className="empty-state" style={{ padding: 20, textAlign: 'center' }}>没有找到物料</div> : assets.map(asset => (
        <div key={asset.id} className={`warehouse-sidebar-item ${selectedAsset?.id === asset.id ? 'selected' : ''}`} onClick={() => onAssetSelect(asset)}>
          <div className="item-header"><span className="item-name">{asset.name}</span><span className="item-status">{asset.available_quantity}</span></div>
          <div className="item-info"><span className="item-category">{asset.primary_category_name}</span><span className="item-category">{asset.secondary_category_name}</span>{asset.low_stock && <span className="item-stock-text" style={{ color: '#dc2626' }}>低库存预警</span>}</div>
        </div>
      ))}
    </div>
  </div>
}

export default WarehouseSidebar
