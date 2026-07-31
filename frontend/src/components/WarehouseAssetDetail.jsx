import { useEffect, useState } from 'react'
import axios from 'axios'
import { X, AlertTriangle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { WarehouseModal } from './Warehouse'

const API_URL = import.meta.env.VITE_API_URL || ''

function WarehouseAssetDetail({ asset, onClose, onRefresh, onBackToHome }) {
  const { isReadOnly } = useAuth()
  const [currentAsset, setCurrentAsset] = useState(asset)
  const [primaryCategories, setPrimaryCategories] = useState([])
  const [migrationIssue, setMigrationIssue] = useState(null)
  const [showEditModal, setShowEditModal] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const loadMaterial = async (id) => {
    try {
      const response = await axios.get(`${API_URL}/warehouse/materials/${id}`)
      setCurrentAsset(response.data)
      return response.data
    } catch (requestError) {
      // 待迁移的历史记录不属于活动物料接口，仍保留调用方提供的数据供只读查看。
      if (!currentAsset) setError(requestError.response?.data?.detail || '获取仓储物料详情失败')
      return null
    }
  }

  const loadMigrationIssue = async (id) => {
    try {
      const response = await axios.get(`${API_URL}/warehouse/category-migration-issues`, { params: { status: 'OPEN' } })
      setMigrationIssue(response.data.find(issue => issue.warehouse_asset_id === id) || null)
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '获取分类待处理信息失败')
    }
  }

  useEffect(() => {
    let active = true
    setCurrentAsset(asset)
    setMigrationIssue(null)
    setError('')
    if (!asset) return undefined
    const initialise = async () => {
      const material = await loadMaterial(asset.id)
      const record = material || asset
      if (active && record?.classification_status === 'PENDING_MIGRATION') await loadMigrationIssue(asset.id)
    }
    initialise()
    return () => { active = false }
  }, [asset])

  useEffect(() => {
    axios.get(`${API_URL}/warehouse/categories/primary`).then(response => setPrimaryCategories(response.data)).catch(() => {})
  }, [])

  if (!currentAsset) return null
  const pendingMigration = currentAsset.classification_status === 'PENDING_MIGRATION'
  const isLowStock = currentAsset.low_stock === true || (currentAsset.available_quantity < currentAsset.low_stock_threshold)
  const totalQuantity = currentAsset.total_quantity ?? ((currentAsset.available_quantity || 0) + (currentAsset.allocated_quantity || 0))

  const saveMaterial = async (form) => {
    try {
      setLoading(true)
      const payload = {
        ...form,
        primary_category_id: Number(form.primary_category_id),
        secondary_category_id: Number(form.secondary_category_id),
        available_quantity: Number(form.available_quantity),
        allocated_quantity: Number(form.allocated_quantity),
        low_stock_threshold: Number(form.low_stock_threshold),
      }
      const response = await axios.put(`${API_URL}/warehouse/materials/${currentAsset.id}`, payload)
      setCurrentAsset(response.data)
      setShowEditModal(false)
      await onRefresh?.()
    } catch (requestError) {
      throw new Error(requestError.response?.data?.detail || '保存仓储物料失败')
    } finally { setLoading(false) }
  }

  return <div className="warehouse-asset-detail-fullpage">
    <div className="warehouse-detail-header">
      <div className="warehouse-detail-title"><h2>{currentAsset.name}</h2>{isLowStock && <span className="stock-status-badge" style={{ backgroundColor: '#dc2626' }}>低库存预警</span>}</div>
      <div className="warehouse-detail-actions-top"><button className="btn btn-secondary" onClick={onBackToHome || onClose}>← 返回主页</button><button className="close-btn" onClick={onClose}><X size={18} /></button></div>
    </div>
    {error && <div className="alert alert-error">{error}</div>}
    <div className="warehouse-detail-content">
      {pendingMigration && <div className="detail-section" style={{ border: '1px solid #f59e0b', background: '#fffbeb' }}>
        <h3 style={{ color: '#92400e' }}><AlertTriangle size={18} /> 分类待处理</h3>
        <p><strong>原分类：</strong>{currentAsset.legacy_category || currentAsset.category || '-'}</p>
        <p><strong>待处理原因：</strong>{migrationIssue?.reason_detail || migrationIssue?.reason_code || '分类映射尚未完成'}</p>
        <p style={{ color: '#92400e' }}>该物料处于只读状态，请由有写权限的用户在分类目录维护中完成一级和二级分类映射。</p>
      </div>}
      <div className="detail-info-block"><div className="detail-section-label">基本信息</div><div className="detail-grid compact">
        <DetailItem label="物料名称" value={currentAsset.name} />
        <DetailItem label="一级分类" value={pendingMigration ? '-' : currentAsset.primary_category_name} />
        <DetailItem label="二级分类" value={pendingMigration ? '-' : currentAsset.secondary_category_name} />
        <DetailItem label="领用策略" value={currentAsset.issue_policy === 'RETURNABLE' ? '待归还' : '一次性消耗品'} />
        <DetailItem label="品牌" value={currentAsset.brand} /><DetailItem label="型号" value={currentAsset.model} /><DetailItem label="存放位置" value={currentAsset.location} />
      </div></div>
      <div className="detail-info-block"><div className="detail-section-label">库存信息</div><div className="stock-overview">
        <StockCard label="总数量" value={totalQuantity} /><StockCard label="可用数量" value={currentAsset.available_quantity} color={isLowStock ? '#dc2626' : undefined} />
        <StockCard label="已分配" value={currentAsset.allocated_quantity} /><StockCard label="低库存阈值" value={currentAsset.low_stock_threshold ?? currentAsset.minimum_stock} />
      </div>
      {isLowStock && <div className="purchase-alert"><div className="alert-icon"><AlertTriangle size={24} color="#dc2626" /></div><div className="alert-content"><div className="alert-title">低库存预警</div><div className="alert-message">可用库存严格低于配置的低库存阈值，请及时补充。</div></div></div>}</div>
      {currentAsset.notes && <div className="detail-section"><h3>备注</h3><div className="notes-content">{currentAsset.notes}</div></div>}
    </div>
    <div className="warehouse-detail-actions">
      {isReadOnly ? <div style={{ color: '#8e9ea4', fontSize: 13 }}>只读模式：仅供查看，不能编辑物料或处理分类迁移。</div> : pendingMigration ? <div style={{ color: '#92400e', fontSize: 13 }}>分类待处理记录不可编辑，请先在分类目录维护中解决。</div> : <button className="btn btn-primary" disabled={loading} onClick={() => setShowEditModal(true)}>编辑物料</button>}
    </div>
    {showEditModal && <WarehouseModal asset={currentAsset} primaryCategories={primaryCategories} onClose={() => setShowEditModal(false)} onSave={saveMaterial} />}
  </div>
}

function DetailItem({ label, value }) { return <div className="detail-item"><div className="detail-label">{label}</div><div className="detail-value">{value || '-'}</div></div> }
function StockCard({ label, value, color }) { return <div className="stock-card" style={color ? { borderColor: color } : undefined}><div className="stock-number font-data" style={color ? { color } : undefined}>{value ?? 0}</div><div className="stock-label">{label}</div></div> }

export default WarehouseAssetDetail
