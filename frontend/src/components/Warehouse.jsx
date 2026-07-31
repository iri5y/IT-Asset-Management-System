import { useEffect, useState } from 'react'
import axios from 'axios'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''
const EMPTY_MATERIAL = {
  name: '', primary_category_id: '', secondary_category_id: '',
  available_quantity: 0, allocated_quantity: 0, low_stock_threshold: 0,
  location: '', issue_policy: 'CONSUMABLE', brand: '', model: '', notes: '',
}

function Warehouse({ selectedAsset, onAssetSelect }) {
  const { isReadOnly } = useAuth()
  const [assets, setAssets] = useState([])
  const [primaryCategories, setPrimaryCategories] = useState([])
  const [secondaryCategories, setSecondaryCategories] = useState([])
  const [filters, setFilters] = useState({ name: '', primary_category_id: '', secondary_category_id: '', low_stock: false })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [editingAsset, setEditingAsset] = useState(null)

  const loadPrimaryCategories = async () => {
    const response = await axios.get(`${API_URL}/warehouse/categories/primary`)
    setPrimaryCategories(response.data)
    return response.data
  }

  const loadSecondaryCategories = async (primaryId) => {
    if (!primaryId) {
      setSecondaryCategories([])
      return []
    }
    const response = await axios.get(`${API_URL}/warehouse/categories/primary/${primaryId}/secondary`)
    setSecondaryCategories(response.data)
    return response.data
  }

  const loadMaterials = async () => {
    try {
      setLoading(true)
      setError('')
      const params = {}
      Object.entries(filters).forEach(([key, value]) => {
        if (value !== '' && value !== false && value !== null) params[key] = value
      })
      const response = await axios.get(`${API_URL}/warehouse/materials`, { params })
      setAssets(response.data)
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '获取仓储物料失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadPrimaryCategories().catch(error => setError(error.response?.data?.detail || '获取一级分类失败')) }, [])
  useEffect(() => { loadMaterials() }, [filters])

  const changeFilter = async (event) => {
    const { name, value, checked, type } = event.target
    if (name === 'primary_category_id') {
      setFilters(current => ({ ...current, primary_category_id: value, secondary_category_id: '' }))
      try { await loadSecondaryCategories(value) } catch (requestError) { setError(requestError.response?.data?.detail || '获取二级分类失败') }
      return
    }
    setFilters(current => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }

  const openAdd = () => {
    setEditingAsset(null)
    setShowModal(true)
  }

  const openEdit = (asset) => {
    setEditingAsset(asset)
    setShowModal(true)
  }

  const saveMaterial = async (material) => {
    const payload = {
      ...material,
      primary_category_id: Number(material.primary_category_id),
      secondary_category_id: Number(material.secondary_category_id),
      available_quantity: Number(material.available_quantity),
      allocated_quantity: Number(material.allocated_quantity),
      low_stock_threshold: Number(material.low_stock_threshold),
    }
    try {
      if (editingAsset) await axios.put(`${API_URL}/warehouse/materials/${editingAsset.id}`, payload)
      else await axios.post(`${API_URL}/warehouse/materials`, payload)
      setShowModal(false)
      await loadMaterials()
    } catch (requestError) {
      throw new Error(requestError.response?.data?.detail || '保存仓储物料失败')
    }
  }

  return (
    <div className="warehouse-container">
      <div className="warehouse-header">
        <div>
          <h2>仓储物料管理</h2>
          <p style={{ margin: 0, color: '#6b7280', fontSize: 13 }}>库房入口仅管理按数量入库的物料，不会创建台式机、笔记本电脑或平板电脑固定资产卡。</p>
        </div>
        {!isReadOnly && <button className="btn btn-primary" onClick={openAdd}>+ 添加仓储物料</button>}
      </div>

      {error && <div className="alert alert-error">{error}</div>}
      <div className="filters">
        <input name="name" value={filters.name} onChange={changeFilter} placeholder="按物料名称筛选" />
        <select name="primary_category_id" value={filters.primary_category_id} onChange={changeFilter}>
          <option value="">所有一级分类</option>
          {primaryCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}
        </select>
        <select name="secondary_category_id" value={filters.secondary_category_id} onChange={changeFilter} disabled={!filters.primary_category_id}>
          <option value="">{filters.primary_category_id ? '所有二级分类' : '请先选择一级分类'}</option>
          {secondaryCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}
        </select>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <input type="checkbox" name="low_stock" checked={filters.low_stock} onChange={changeFilter} /> 仅显示低库存预警
        </label>
      </div>

      {loading ? <div className="loading">加载中...</div> : assets.length === 0 ? (
        <div className="empty-state"><h3>没有符合条件的仓储物料</h3><p>可调整筛选条件，或添加第一条物料记录。</p></div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="data-table" style={{ width: '100%' }}>
            <thead><tr><th>物料名称</th><th>一级分类</th><th>二级分类</th><th>可用数量</th><th>已分配</th><th>存放位置</th><th>低库存阈值</th><th>状态</th>{!isReadOnly && <th>操作</th>}</tr></thead>
            <tbody>{assets.map(asset => (
              <tr key={asset.id} onClick={() => onAssetSelect?.(asset)} style={{ cursor: onAssetSelect ? 'pointer' : 'default' }} className={selectedAsset?.id === asset.id ? 'selected' : ''}>
                <td>{asset.name}</td><td>{asset.primary_category_name}</td><td>{asset.secondary_category_name}</td>
                <td>{asset.available_quantity}</td><td>{asset.allocated_quantity}</td><td>{asset.location || '-'}</td><td>{asset.low_stock_threshold}</td>
                <td>{asset.low_stock ? <span style={{ color: '#dc2626', fontWeight: 600 }}>低库存预警</span> : '库存正常'}</td>
                {!isReadOnly && <td><button className="btn btn-secondary" onClick={(event) => { event.stopPropagation(); openEdit(asset) }}>编辑</button></td>}
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}

      {showModal && <WarehouseModal asset={editingAsset} primaryCategories={primaryCategories} onLoadSecondary={loadSecondaryCategories} onClose={() => setShowModal(false)} onSave={saveMaterial} />}
    </div>
  )
}

function WarehouseModal({ asset, primaryCategories: suppliedPrimaryCategories, onLoadSecondary, onClose, onSave }) {
  const [form, setForm] = useState(EMPTY_MATERIAL)
  const [primaryCategories, setPrimaryCategories] = useState(suppliedPrimaryCategories || [])
  const [secondaryCategories, setSecondaryCategories] = useState([])
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const fetchPrimary = async () => {
    if (suppliedPrimaryCategories?.length) return suppliedPrimaryCategories
    const response = await axios.get(`${API_URL}/warehouse/categories/primary`)
    setPrimaryCategories(response.data)
    return response.data
  }
  const fetchSecondary = async (primaryId) => {
    if (!primaryId) { setSecondaryCategories([]); return [] }
    const items = onLoadSecondary ? await onLoadSecondary(primaryId) : (await axios.get(`${API_URL}/warehouse/categories/primary/${primaryId}/secondary`)).data
    setSecondaryCategories(items)
    return items
  }

  useEffect(() => {
    let active = true
    const initialise = async () => {
      try {
        await fetchPrimary()
        if (!asset) { if (active) setForm(EMPTY_MATERIAL); return }
        const primaryId = String(asset.primary_category_id || '')
        if (active) setForm({
          name: asset.name || '', primary_category_id: primaryId, secondary_category_id: '',
          available_quantity: asset.available_quantity ?? 0, allocated_quantity: asset.allocated_quantity ?? 0,
          low_stock_threshold: asset.low_stock_threshold ?? asset.minimum_stock ?? 0, location: asset.location || '',
          issue_policy: asset.issue_policy || 'CONSUMABLE', brand: asset.brand || '', model: asset.model || '', notes: asset.notes || '',
        })
        const children = await fetchSecondary(primaryId)
        if (active && children.some(item => item.id === asset.secondary_category_id)) {
          setForm(current => ({ ...current, secondary_category_id: String(asset.secondary_category_id) }))
        }
      } catch (requestError) {
        if (active) setError(requestError.response?.data?.detail || '加载分类失败')
      }
    }
    initialise()
    return () => { active = false }
  }, [asset])

  const changeValue = async (event) => {
    const { name, value } = event.target
    if (name === 'primary_category_id') {
      setForm(current => ({ ...current, primary_category_id: value, secondary_category_id: '' }))
      setError('')
      try { await fetchSecondary(value) } catch (requestError) { setError(requestError.response?.data?.detail || '获取二级分类失败') }
      return
    }
    setForm(current => ({ ...current, [name]: value }))
  }

  const submit = async (event) => {
    event.preventDefault()
    const validSecondary = secondaryCategories.some(category => String(category.id) === String(form.secondary_category_id))
    if (!form.primary_category_id || !form.secondary_category_id || !validSecondary) {
      setError('请选择有效且从属的一级分类与二级分类。')
      return
    }
    try {
      setSaving(true)
      setError('')
      await onSave(form)
    } catch (requestError) {
      setError(requestError.message || '保存仓储物料失败')
    } finally { setSaving(false) }
  }

  return <div className="modal-overlay" onClick={onClose}><div className="modal-content" onClick={event => event.stopPropagation()}>
    <div className="modal-header"><h2>{asset ? '编辑仓储物料' : '添加仓储物料'}</h2><button className="close-btn" onClick={onClose}>&times;</button></div>
    <form onSubmit={submit}><div className="modal-body">
      {error && <div className="form-error">{error}</div>}
      <div className="form-row"><div className="form-group"><label>物料名称 *</label><input name="name" required value={form.name} onChange={changeValue} /></div><div className="form-group"><label>领用策略 *</label><select name="issue_policy" value={form.issue_policy} onChange={changeValue}><option value="CONSUMABLE">一次性消耗品</option><option value="RETURNABLE">待归还</option></select></div></div>
      <div className="form-row"><div className="form-group"><label>一级分类 *</label><select name="primary_category_id" required value={form.primary_category_id} onChange={changeValue}><option value="">选择一级分类</option>{primaryCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></div><div className="form-group"><label>二级分类 *</label><select name="secondary_category_id" required disabled={!form.primary_category_id} value={form.secondary_category_id} onChange={changeValue}><option value="">{form.primary_category_id ? '选择二级分类' : '请先选择一级分类'}</option>{secondaryCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></div></div>
      <div className="form-row"><div className="form-group"><label>可用数量 *</label><input type="number" min="0" name="available_quantity" required value={form.available_quantity} onChange={changeValue} /></div><div className="form-group"><label>已分配数量 *</label><input type="number" min="0" name="allocated_quantity" required value={form.allocated_quantity} onChange={changeValue} /></div></div>
      <div className="form-row"><div className="form-group"><label>低库存阈值 *</label><input type="number" min="0" name="low_stock_threshold" required value={form.low_stock_threshold} onChange={changeValue} /></div><div className="form-group"><label>存放位置</label><input name="location" value={form.location} onChange={changeValue} /></div></div>
      <div className="form-row"><div className="form-group"><label>品牌</label><input name="brand" value={form.brand} onChange={changeValue} /></div><div className="form-group"><label>型号</label><input name="model" value={form.model} onChange={changeValue} /></div></div>
      <div className="form-group"><label>备注</label><textarea name="notes" rows="3" value={form.notes} onChange={changeValue} /></div>
    </div><div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={onClose}>取消</button><button type="submit" className="btn btn-primary" disabled={saving}>{saving ? '保存中...' : '保存'}</button></div></form>
  </div></div>
}

export default Warehouse
export { WarehouseModal }
