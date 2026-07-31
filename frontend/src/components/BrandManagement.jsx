import { useState, useEffect } from 'react'
import axios from 'axios'
import { Tag, Plus, Trash2 } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function BrandManagement() {
  const [brands, setBrands] = useState([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')
  const [adding, setAdding] = useState(false)

  useEffect(() => { fetchBrands() }, [])

  const fetchBrands = async () => {
    try {
      setLoading(true)
      const res = await axios.get(`${API_URL}/brands/`)
      setBrands(res.data)
    } catch (err) {
      console.error('获取品牌列表失败:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      setAdding(true)
      await axios.post(`${API_URL}/brands/`, { name })
      setNewName('')
      fetchBrands()
    } catch (err) {
      alert('添加失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (brand) => {
    if (!window.confirm(`确定要删除品牌"${brand.name}"吗？`)) return
    try {
      await axios.delete(`${API_URL}/brands/${brand.id}`)
      fetchBrands()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  return (
    <div className="user-management-page">
      <div className="page-header">
        <h2>品牌管理</h2>
      </div>
      <p style={{ color: '#8E9EA4', fontSize: 13, marginBottom: 20 }}>管理资产品牌列表，共 {brands.length} 个品牌</p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          placeholder="输入新品牌名称..."
          style={{ flex: 1, padding: '10px 14px', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', fontSize: 14 }}
        />
        <button className="btn btn-primary" onClick={handleAdd} disabled={adding || !newName.trim()}>
          <Plus size={16} /> 添加
        </button>
      </div>

      {loading ? (
        <div className="loading">加载中...</div>
      ) : brands.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><Tag size={48} /></div>
          <h3>暂无品牌</h3>
          <p>添加第一个品牌开始管理</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}>
          {brands.map(brand => (
            <div key={brand.id} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 14px', background: 'var(--color-surface)',
              border: '1px solid var(--color-border)', borderRadius: 'var(--radius)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Tag size={14} style={{ color: 'var(--color-primary)' }} />
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-heading)' }}>{brand.name}</span>
              </div>
              <button className="btn btn-sm btn-danger" onClick={() => handleDelete(brand)} title="删除">
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default BrandManagement
