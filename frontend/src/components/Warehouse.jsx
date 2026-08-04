import { useState, useEffect } from 'react'
import axios from 'axios'
import {useAuth} from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''

function Warehouse({ selectedAsset, onAssetSelect }) {
  const {isReadonly} = useAuth()
  const [assets, setAssets] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editingAsset, setEditingAsset] = useState(null)
  const [filters, setFilters] = useState({
    search: '',
    category: '',
    low_stock: false
  })

  useEffect(() => {
    fetchAssets()
    fetchStats()
  }, [filters])

  const fetchAssets = async () => {
    try {
      setLoading(true)
      const params = {}
      Object.keys(filters).forEach(key => {
        if (filters[key]) params[key] = filters[key]
      })
      const response = await axios.get(`${API_URL}/warehouse/`, { params })
      setAssets(response.data)
    } catch (error) {
      console.error('获取库房资产失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const fetchStats = async () => {
    try {
      const response = await axios.get(`${API_URL}/warehouse/stats`)
      setStats(response.data)
    } catch (error) {
      console.error('获取统计数据失败:', error)
    }
  }

  const handleAddAsset = () => {
    setEditingAsset(null)
    setShowModal(true)
  }

  const handleEditAsset = (asset) => {
    setEditingAsset(asset)
    setShowModal(true)
  }

  const handleDeleteAsset = async (id) => {
    if (!window.confirm('确定要删除这个库房资产吗？')) return
    
    try {
      await axios.delete(`${API_URL}/warehouse/${id}`)
      fetchAssets()
      fetchStats()
    } catch (error) {
      console.error('删除库房资产失败:', error)
      alert('删除库房资产失败')
    }
  }

  const handleSaveAsset = async (assetData) => {
    try {
      if (editingAsset) {
        await axios.put(`${API_URL}/warehouse/${editingAsset.id}`, assetData)
      } else {
        await axios.post(`${API_URL}/warehouse/`, assetData)
      }
      setShowModal(false)
      fetchAssets()
      fetchStats()
    } catch (error) {
      console.error('保存库房资产失败:', error)
      alert('保存库房资产失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const handleFilterChange = (e) => {
    const { name, value, type, checked } = e.target
    setFilters({
      ...filters,
      [name]: type === 'checkbox' ? checked : value
    })
  }

  const getStockStatus = (asset) => {
    if (asset.available_quantity <= asset.minimum_stock) {
      return { status: 'low', color: '#E05252', text: '库存不足' }
    } else if (asset.available_quantity <= asset.minimum_stock * 2) {
      return { status: 'medium', color: '#D4952B', text: '库存偏低' }
    } else {
      return { status: 'good', color: '#3A9E75', text: '库存充足' }
    }
  }

  // 按品类分组资产
  const assetsByCategory = assets.reduce((groups, asset) => {
    const cat = asset.category || '未分类'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(asset)
    return groups
  }, {})

  // 品类颜色映射
  const categoryColors = {
    '计算机设备': '#184e77', '显示设备': '#1e6091', '移动设备': '#1a759f', '输入设备': '#168aad',
    '存储设备': '#34a0a4', '网络设备': '#52b69a', '其他配件': '#76c893', '未分类': '#99d98c'
  }

  return (
    <div className="warehouse-container">
      <div className="warehouse-header">
        <h2>IT资产库房管理</h2>
        {!isReadonly && (
        <button className="btn btn-primary" onClick={handleAddAsset}>
          + 添加库房资产
        </button>
        )}
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

      {/* 过滤器 */}
      <div className="filters">
        <input
          type="text"
          name="search"
          placeholder="搜索资产名称、品牌、型号..."
          value={filters.search}
          onChange={handleFilterChange}
        />
        <select name="category" value={filters.category} onChange={handleFilterChange}>
          <option value="">所有品类</option>
          <option value="显示设备">显示设备</option>
          <option value="输入设备">输入设备</option>
          <option value="存储设备">存储设备</option>
          <option value="网络设备">网络设备</option>
          <option value="其他配件">其他配件</option>
        </select>
        <label style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <input
            type="checkbox"
            name="low_stock"
            checked={filters.low_stock}
            onChange={handleFilterChange}
          />
          仅显示库存不足
        </label>
      </div>

      {/* 资产列表 - 按位置分组 */}
      {loading ? (
        <div className="loading">加载中...</div>
      ) : assets.length === 0 ? (
        <div className="empty-state">
          <h3>没有找到库房资产</h3>
          <p>添加第一个库房资产开始管理</p>
        </div>
      ) : (
        <div className="warehouse-by-location">
          {Object.entries(assetsByCategory).map(([category, catAssets]) => (
            <div key={category} className="location-section">
              <div className="location-header" style={{ borderLeftColor: categoryColors[category] || '#8E9EA4' }}>
                <h3>{category}</h3>
                <span className="location-count">{catAssets.length} 种资产</span>
              </div>
              <div className="location-assets-grid">
                {catAssets.map(asset => {
                  const stockStatus = getStockStatus(asset)
                  return (
                    <div 
                      key={asset.id} 
                      className={`warehouse-grid-card ${selectedAsset && selectedAsset.id === asset.id ? 'selected' : ''}`}
                      onClick={() => onAssetSelect && onAssetSelect(asset)}
                    >
                      <div className="grid-card-header">
                        <span className="grid-card-name">{asset.name}</span>
                        <span 
                          className="grid-card-status"
                          style={{ backgroundColor: stockStatus.color }}
                        >
                          {asset.available_quantity}
                        </span>
                      </div>
                      <div className="grid-card-info">
                        {asset.location && <span className="grid-card-category">{asset.location}</span>}
                        {asset.model && <span className="grid-card-model">{asset.model}</span>}
                      </div>
                      <div className="grid-card-quantity">
                        <span>可用: <strong className="font-data">{asset.available_quantity}</strong></span>
                        <span>总数: <span className="font-data">{asset.total_quantity}</span></span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 模态框 */}
      {showModal && (
        <WarehouseModal
          asset={editingAsset}
          onClose={() => setShowModal(false)}
          onSave={handleSaveAsset}
        />
      )}
    </div>
  )
}

function WarehouseModal({ asset, onClose, onSave }) {
  const [formData, setFormData] = useState({
    name: '',
    category: '',
    subcategory: '',
    brand: '',
    model: '',
    receiver_name: '',
    received_date: new Date().toISOString().split('T')[0],
    total_quantity: 0,
    available_quantity: 0,
    allocated_quantity: 0,
    minimum_stock: 5,
    location: '',
    notes: ''
  })
  
  const [locations, setLocations] = useState([
    'IT库房',
    'A区货架',
    'B区货架', 
    'C区货架',
    '临时存放区',
    '办公区域'
  ])
  
  const [users, setUsers] = useState([])
  const [brands, setBrands] = useState([])

  useEffect(() => {
    axios.get(`${API_URL}/locations/`).then(res => setLocations(res.data.map(l => l.name))).catch(() => {})
    axios.get(`${API_URL}/brands/`).then(res => setBrands(res.data)).catch(() => {})
    fetchUsers()
    
    if (asset) {
      setFormData({
        name: asset.name || '',
        category: asset.category || '',
        subcategory: asset.subcategory || '',
        brand: asset.brand || '',
        model: asset.model || '',
        receiver_name: asset.receiver_name || '',
        received_date: asset.received_date ? asset.received_date.split('T')[0] : new Date().toISOString().split('T')[0],
        total_quantity: asset.total_quantity || 0,
        available_quantity: asset.available_quantity || 0,
        allocated_quantity: asset.allocated_quantity || 0,
        minimum_stock: asset.minimum_stock || 5,
        location: asset.location || '',
        notes: asset.notes || ''
      })
    }
  }, [asset])

  const fetchUsers = async () => {
    try {
      const response = await axios.get(`${API_URL}/auth/mis-users`)
      setUsers(response.data)
    } catch (error) {
      console.error('获取用户列表失败:', error)
    }
  }

  const handleChange = (e) => {
    const { name, value, type } = e.target
    if (type === 'number') {
      // 允许完全删除数字，避免010这样的情况
      if (value === '') {
        setFormData({ ...formData, [name]: '' })
      } else {
        const numValue = parseInt(value)
        setFormData({ ...formData, [name]: isNaN(numValue) ? 0 : numValue })
      }
    } else {
      setFormData({ ...formData, [name]: value })
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{asset ? '编辑库房资产' : '添加库房资产'}</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          <div className="modal-body">
            <div className="form-row">
              <div className="form-group">
                <label>资产名称 *</label>
                <input
                  type="text"
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                  required
                />
              </div>
              <div className="form-group">
                <label>品类 *</label>
                <select name="category" value={formData.category} onChange={handleChange} required>
                  <option value="">选择品类</option>
                  <option value="显示设备">显示设备</option>
                  <option value="输入设备">输入设备</option>
                  <option value="存储设备">存储设备</option>
                  <option value="网络设备">网络设备</option>
                  <option value="其他配件">其他配件</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>子分类</label>
                <input type="text" name="subcategory" value={formData.subcategory} onChange={handleChange} />
              </div>
              <div className="form-group">
                <label>品牌</label>
                <select name="brand" value={formData.brand} onChange={handleChange}>
                  <option value="">选择品牌</option>
                  {brands.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>型号</label>
                <input type="text" name="model" value={formData.model} onChange={handleChange} />
              </div>
              <div className="form-group">
                <label>入库人 *</label>
                <select name="receiver_name" value={formData.receiver_name} onChange={handleChange} required>
                  <option value="">选择入库人</option>
                  {users.map(user => (
                    <option key={user.id} value={user.username}>{user.username}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>入库日期 *</label>
                <input 
                  type="date" 
                  name="received_date" 
                  value={formData.received_date} 
                  onChange={handleChange} 
                  required 
                />
              </div>
              <div className="form-group">
                <label>总数量 *</label>
                <input
                  type="number"
                  name="total_quantity"
                  value={formData.total_quantity}
                  onChange={handleChange}
                  min="0"
                  required
                />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>可用数量 *</label>
                <input
                  type="number"
                  name="available_quantity"
                  value={formData.available_quantity}
                  onChange={handleChange}
                  min="0"
                  required
                />
              </div>
              <div className="form-group">
                <label>已分配数量</label>
                <input
                  type="number"
                  name="allocated_quantity"
                  value={formData.allocated_quantity}
                  onChange={handleChange}
                  min="0"
                />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>最低库存</label>
                <input
                  type="number"
                  name="minimum_stock"
                  value={formData.minimum_stock}
                  onChange={handleChange}
                  min="1"
                />
              </div>
              <div className="form-group">
                {/* 空白占位 */}
              </div>
            </div>
            <div className="form-group">
              <label>存放位置</label>
              <select name="location" value={formData.location} onChange={handleChange}>
                <option value="">选择位置</option>
                {locations.map(location => (
                  <option key={location} value={location}>{location}</option>
                ))}
              </select>
            </div>
            <div className="form-group">
              <label>备注</label>
              <textarea name="notes" value={formData.notes} onChange={handleChange} rows="3" />
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>取消</button>
            <button type="submit" className="btn btn-primary">保存</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default Warehouse
export { WarehouseModal }