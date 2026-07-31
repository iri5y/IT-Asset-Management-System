import { useState, useEffect } from 'react'
import axios from 'axios'
import { Building2, Plus, Trash2, ChevronDown, ChevronRight } from 'lucide-react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function DepartmentManagement() {
  const [tree, setTree] = useState([])
  const [loading, setLoading] = useState(true)
  const [newParentName, setNewParentName] = useState('')
  const [addingChildFor, setAddingChildFor] = useState(null)
  const [newChildName, setNewChildName] = useState('')
  const [expanded, setExpanded] = useState({})

  useEffect(() => { fetchTree() }, [])

  const fetchTree = async () => {
    try {
      setLoading(true)
      const res = await axios.get(`${API_URL}/departments/`)
      setTree(res.data)
      // 默认全部展开
      const exp = {}
      res.data.forEach(p => { exp[p.id] = true })
      setExpanded(exp)
    } catch (err) {
      console.error('获取部门失败:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleAddParent = async () => {
    const name = newParentName.trim()
    if (!name) return
    try {
      await axios.post(`${API_URL}/departments/`, { name })
      setNewParentName('')
      fetchTree()
    } catch (err) {
      alert('添加失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const handleAddChild = async (parentId) => {
    const name = newChildName.trim()
    if (!name) return
    try {
      await axios.post(`${API_URL}/departments/`, { name, parent_id: parentId })
      setNewChildName('')
      setAddingChildFor(null)
      fetchTree()
    } catch (err) {
      alert('添加失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const handleDelete = async (dept, isParent) => {
    const msg = isParent
      ? `确定要删除主分类"${dept.name}"及其所有子分类吗？`
      : `确定要删除子分类"${dept.name}"吗？`
    if (!window.confirm(msg)) return
    try {
      await axios.delete(`${API_URL}/departments/${dept.id}`)
      fetchTree()
    } catch (err) {
      alert('删除失败: ' + (err.response?.data?.detail || err.message))
    }
  }

  const toggleExpand = (id) => {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }))
  }

  return (
    <div className="user-management-page">
      <div className="page-header">
        <h2>部门管理</h2>
      </div>
      <p style={{ color: '#8E9EA4', fontSize: 13, marginBottom: 20 }}>
        管理部门结构（主分类 → 子分类），共 {tree.length} 个主分类
      </p>

      {/* 添加主分类 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        <input
          type="text"
          value={newParentName}
          onChange={(e) => setNewParentName(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAddParent()}
          placeholder="输入主分类名称（如：销售中心）..."
          style={{ flex: 1, padding: '10px 14px', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', fontSize: 14 }}
        />
        <button className="btn btn-primary" onClick={handleAddParent} disabled={!newParentName.trim()}>
          <Plus size={16} /> 添加主分类
        </button>
      </div>

      {loading ? (
        <div className="loading">加载中...</div>
      ) : tree.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon"><Building2 size={48} /></div>
          <h3>暂无部门</h3>
          <p>添加第一个主分类开始管理</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {tree.map(parent => (
            <div key={parent.id} style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
              {/* 主分类 */}
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '12px 16px', background: 'var(--color-bg)', cursor: 'pointer'
              }} onClick={() => toggleExpand(parent.id)}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {expanded[parent.id] ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  <Building2 size={16} style={{ color: 'var(--color-primary)' }} />
                  <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--color-heading)' }}>{parent.name}</span>
                  <span style={{ fontSize: 11, color: 'var(--color-muted)' }}>({parent.children.length} 个子分类)</span>
                </div>
                <div style={{ display: 'flex', gap: 6 }} onClick={(e) => e.stopPropagation()}>
                  <button className="btn btn-sm btn-secondary" onClick={() => { setAddingChildFor(addingChildFor === parent.id ? null : parent.id); setNewChildName('') }}>
                    <Plus size={13} /> 子分类
                  </button>
                  <button className="btn btn-sm btn-danger" onClick={() => handleDelete(parent, true)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              {/* 子分类列表 */}
              {expanded[parent.id] && (
                <div style={{ padding: '0 16px 12px 44px' }}>
                  {/* 添加子分类输入框 */}
                  {addingChildFor === parent.id && (
                    <div style={{ display: 'flex', gap: 6, marginTop: 10, marginBottom: 6 }}>
                      <input
                        type="text"
                        value={newChildName}
                        onChange={(e) => setNewChildName(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAddChild(parent.id)}
                        placeholder="输入子分类名称..."
                        autoFocus
                        style={{ flex: 1, padding: '7px 10px', border: '1px solid var(--color-border)', borderRadius: 'var(--radius)', fontSize: 13 }}
                      />
                      <button className="btn btn-sm btn-primary" onClick={() => handleAddChild(parent.id)} disabled={!newChildName.trim()}>确认</button>
                      <button className="btn btn-sm btn-secondary" onClick={() => setAddingChildFor(null)}>取消</button>
                    </div>
                  )}
                  {parent.children.length === 0 && addingChildFor !== parent.id && (
                    <div style={{ padding: '8px 0', color: 'var(--color-muted)', fontSize: 12 }}>暂无子分类</div>
                  )}
                  {parent.children.map(child => (
                    <div key={child.id} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                      padding: '8px 12px', marginTop: 4, background: 'var(--color-surface)',
                      border: '1px solid var(--color-border)', borderRadius: 'var(--radius)',
                    }}>
                      <span style={{ fontSize: 13, color: 'var(--color-body)' }}>{child.name}</span>
                      <button className="btn btn-sm btn-danger" onClick={() => handleDelete(child, false)} style={{ padding: '3px 6px' }}>
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default DepartmentManagement
