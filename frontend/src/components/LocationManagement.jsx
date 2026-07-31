import { useState, useEffect } from 'react'
import axios from 'axios'
import { MapPin, Plus, Trash2 } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || ''

function LocationManagement({ type = 'warehouse'}) {
  const [locations, setLocations] = useState([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [adding, setAdding] = useState(false)

  const isoffice = type === 'office'
  const endpoint = isoffice ? '/office-locations/' : '/locations/'
  const pageTitle = isoffice ? '办公资产位置管理' : '库房位置管理'
  const pageDesc = isoffice ? '管理台式机等资产的使用位置' : '管理库房存放位置'
  const namePlaceholder = isoffice ? '例如：L1、OA办公室...' : '输入新位置名称...'
  const descPlaceholder = isoffice ? '例如：1号楼办公室（可选）' : '例如：A区货架-第2排（可选）'

  useEffect(() => { fetchLocations() }, [type])

  const fetchLocations = async () => {
    try {
      setLoading(true)
      const res = await axios.get(`${API_URL}${endpoint}`)
      setLocations(res.data)
    } catch (err) {
      console.error(`获取${pageTitle}位置列表失败:`, err)
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async () => {
    const name = newName.trim()
    if (!name) return
    try {
      setAdding(true)
      await axios.post(`${API_URL}${endpoint}`, {
        name,
        description: newDescription.trim() || null,
      })
      setNewName('')
      setNewDescription('')
      fetchLocations()
    } catch (err) {
      alert('添加失败: ' + (err.response?.data?.detail || err.message))
    } finally {
      setAdding(false)
    }
  }

  const handleDelete = async (loc) => {
    if (!window.confirm(`确定要删除位置"${loc.name}"吗？`)) return
    try {
      await axios.delete(`${API_URL}${endpoint}${loc.id}`)
      fetchLocations()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 20, marginBottom: 4 }}>{pageTitle}</h2>
          <p style={{ color: '#8E9EA4', fontSize: 13 }}>{pageDesc}，共 {locations.length} 个</p>
        </div>
      </div>

      {/* 添加新位置 */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
            placeholder={namePlaceholder}
            style={{ flex: 1, padding: '10px 14px', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', fontSize: 14 }}
          />
          <button className="btn btn-primary" onClick={handleAdd} disabled={adding || !newName.trim()}>
            <Plus size={16} /> 添加
          </button>
        </div>
        <input
          type="text"
          value={newDescription}
          onChange={(e) => setNewDescription(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
          placeholder={descPlaceholder}
          style={{ padding: '10px 14px', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', fontSize: 14, color: 'var(--color-muted)' }}
        />
      </div>

      {/* 位置列表 */}
      {loading ? (
        <div className="loading">加载中...</div>
      ) : locations.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><MapPin size={48} /></div>
          <h3>暂无{pageTitle.replace('管理', '')}</h3>
          <p>{isoffice ? '添加第一个资产位置开始管理' : '添加第一个库房位置开始管理'}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {locations.map(loc => (
            <div key={loc.id} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '12px 16px', background: 'var(--color-surface)',
              border: '1px solid var(--color-border)', borderRadius: 'var(--radius)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <MapPin size={16} style={{ color: 'var(--color-primary)', flexShrink: 0 }} />
                <div>
                  <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--color-heading)' }}>{loc.name}</span>
                  {loc.description && (
                    <span style={{ fontSize: 12, color: 'var(--color-muted)', marginLeft: 10 }}>
                      {loc.description}
                    </span>
                  )}
                </div>
              </div>
              <button
                className="btn btn-sm btn-danger"
                onClick={() => handleDelete(loc)}
                title="删除此位置"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default LocationManagement
