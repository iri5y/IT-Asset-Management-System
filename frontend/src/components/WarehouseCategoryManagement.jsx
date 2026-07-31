import { useEffect, useMemo, useState } from 'react'
import axios from 'axios'
import { useAuth } from '../contexts/AuthContext'

const API_URL = import.meta.env.VITE_API_URL || ''
const EMPTY_PRIMARY = { id: null, code: '', name: '', sort_order: 0 }
const EMPTY_SECONDARY = { id: null, primary_category_id: '', code: '', name: '', sort_order: 0 }

function WarehouseCategoryManagement() {
  const { isReadOnly } = useAuth()
  const [categories, setCategories] = useState([])
  const [issues, setIssues] = useState([])
  const [selectedPrimaryId, setSelectedPrimaryId] = useState('')
  const [primaryForm, setPrimaryForm] = useState(EMPTY_PRIMARY)
  const [secondaryForm, setSecondaryForm] = useState(EMPTY_SECONDARY)
  const [resolvingIssue, setResolvingIssue] = useState(null)
  const [resolution, setResolution] = useState({ primary_category_id: '', secondary_category_id: '', resolution_note: '' })
  const [resolutionSecondaryCategories, setResolutionSecondaryCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const selectedPrimary = useMemo(() => categories.find(category => String(category.id) === String(selectedPrimaryId)) || null, [categories, selectedPrimaryId])

  const loadData = async () => {
    try {
      setLoading(true)
      setError('')
      const categoryRequest = axios.get(`${API_URL}/warehouse/categories`, { params: isReadOnly ? {} : { include_inactive: true } })
      const issueRequest = axios.get(`${API_URL}/warehouse/category-migration-issues`, { params: { status: 'OPEN' } })
      const [categoryResponse, issueResponse] = await Promise.all([categoryRequest, issueRequest])
      setCategories(categoryResponse.data.categories)
      setIssues(issueResponse.data)
      setSelectedPrimaryId(current => current || String(categoryResponse.data.categories[0]?.id || ''))
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '加载分类目录失败')
    } finally { setLoading(false) }
  }

  useEffect(() => { loadData() }, [isReadOnly])

  const requestError = (errorValue, fallback) => errorValue.response?.data?.detail || errorValue.message || fallback
  const updatePrimaryForm = event => setPrimaryForm(current => ({ ...current, [event.target.name]: event.target.value }))
  const updateSecondaryForm = event => setSecondaryForm(current => ({ ...current, [event.target.name]: event.target.value }))

  const submitPrimary = async event => {
    event.preventDefault()
    try {
      setSaving(true); setError('')
      const payload = { code: primaryForm.code, name: primaryForm.name, sort_order: Number(primaryForm.sort_order) }
      if (primaryForm.id) await axios.patch(`${API_URL}/warehouse/categories/primary/${primaryForm.id}`, payload)
      else await axios.post(`${API_URL}/warehouse/categories/primary`, payload)
      setPrimaryForm(EMPTY_PRIMARY)
      await loadData()
    } catch (errorValue) { setError(requestError(errorValue, '保存一级分类失败')) } finally { setSaving(false) }
  }

  const submitSecondary = async event => {
    event.preventDefault()
    try {
      setSaving(true); setError('')
      const payload = { code: secondaryForm.code, name: secondaryForm.name, sort_order: Number(secondaryForm.sort_order) }
      if (secondaryForm.id) await axios.patch(`${API_URL}/warehouse/categories/secondary/${secondaryForm.id}`, payload)
      else await axios.post(`${API_URL}/warehouse/categories/secondary`, { ...payload, primary_category_id: Number(secondaryForm.primary_category_id) })
      setSecondaryForm(EMPTY_SECONDARY)
      await loadData()
    } catch (errorValue) { setError(requestError(errorValue, '保存二级分类失败')) } finally { setSaving(false) }
  }

  const changeActiveState = async (level, category) => {
    try {
      setSaving(true); setError('')
      await axios.patch(`${API_URL}/warehouse/categories/${level}/${category.id}`, { is_active: !category.is_active })
      await loadData()
    } catch (errorValue) { setError(requestError(errorValue, `更新${level === 'primary' ? '一级' : '二级'}分类状态失败`)) } finally { setSaving(false) }
  }

  const beginResolution = issue => {
    setResolvingIssue(issue)
    setResolution({ primary_category_id: '', secondary_category_id: '', resolution_note: '' })
    setResolutionSecondaryCategories([])
  }

  const changeResolutionPrimary = async event => {
    const primaryId = event.target.value
    setResolution(current => ({ ...current, primary_category_id: primaryId, secondary_category_id: '' }))
    setResolutionSecondaryCategories([])
    if (!primaryId) return
    try {
      const response = await axios.get(`${API_URL}/warehouse/categories/primary/${primaryId}/secondary`)
      setResolutionSecondaryCategories(response.data)
    } catch (errorValue) { setError(requestError(errorValue, '获取二级分类失败')) }
  }

  const resolveIssue = async event => {
    event.preventDefault()
    const validSecondary = resolutionSecondaryCategories.some(category => String(category.id) === String(resolution.secondary_category_id))
    if (!resolution.primary_category_id || !validSecondary) { setError('请选择有效且从属的一级分类与二级分类。'); return }
    try {
      setSaving(true); setError('')
      await axios.post(`${API_URL}/warehouse/category-migration-issues/${resolvingIssue.id}/resolve`, {
        primary_category_id: Number(resolution.primary_category_id), secondary_category_id: Number(resolution.secondary_category_id), resolution_note: resolution.resolution_note || null,
      })
      setResolvingIssue(null)
      await loadData()
    } catch (errorValue) { setError(requestError(errorValue, '解决分类待处理项失败')) } finally { setSaving(false) }
  }

  const startSecondaryCreation = () => setSecondaryForm({ ...EMPTY_SECONDARY, primary_category_id: selectedPrimaryId })

  return <div className="warehouse-container">
    <div className="warehouse-header"><div><h2>仓储分类目录维护</h2><p style={{ margin: 0, color: '#6b7280', fontSize: 13 }}>分类只能新增、改名、排序或启停；不支持硬删除和直接修改二级分类所属一级分类。</p></div></div>
    {error && <div className="alert alert-error">{error}</div>}
    {isReadOnly && <div className="alert">只读模式：可查看分类目录和待处理报告，不能维护分类或解决迁移问题。</div>}
    {loading ? <div className="loading">加载中...</div> : <>
      <div className="form-row" style={{ alignItems: 'flex-start' }}>
        <div className="form-group" style={{ flex: 1 }}><label>按一级分类查看二级分类</label><select value={selectedPrimaryId} onChange={event => setSelectedPrimaryId(event.target.value)}><option value="">选择一级分类</option>{categories.map(category => <option key={category.id} value={category.id}>{category.name}{category.is_active ? '' : '（已停用）'}</option>)}</select></div>
      </div>
      <div style={{ overflowX: 'auto' }}><table className="data-table" style={{ width: '100%' }}><thead><tr><th>代码</th><th>一级分类</th><th>排序</th><th>状态</th>{!isReadOnly && <th>维护</th>}</tr></thead><tbody>{categories.map(category => <tr key={category.id}><td>{category.code}</td><td>{category.name}</td><td>{category.sort_order}</td><td>{category.is_active ? '启用' : '停用'}</td>{!isReadOnly && <td><button className="btn btn-secondary" onClick={() => setPrimaryForm({ id: category.id, code: category.code, name: category.name, sort_order: category.sort_order })}>改名/排序</button><button className="btn btn-secondary" disabled={saving} onClick={() => changeActiveState('primary', category)}>{category.is_active ? '停用' : '启用'}</button></td>}</tr>)}</tbody></table></div>
      {selectedPrimary && <><h3 style={{ marginTop: 24 }}>{selectedPrimary.name} 的二级分类</h3><div style={{ overflowX: 'auto' }}><table className="data-table" style={{ width: '100%' }}><thead><tr><th>代码</th><th>二级分类</th><th>排序</th><th>状态</th>{!isReadOnly && <th>维护</th>}</tr></thead><tbody>{selectedPrimary.secondary_categories.map(category => <tr key={category.id}><td>{category.code}</td><td>{category.name}</td><td>{category.sort_order}</td><td>{category.is_active ? '启用' : '停用'}</td>{!isReadOnly && <td><button className="btn btn-secondary" onClick={() => setSecondaryForm({ id: category.id, primary_category_id: String(category.primary_category_id), code: category.code, name: category.name, sort_order: category.sort_order })}>改名/排序</button><button className="btn btn-secondary" disabled={saving} onClick={() => changeActiveState('secondary', category)}>{category.is_active ? '停用' : '启用'}</button></td>}</tr>)}</tbody></table></div></>}
      {!isReadOnly && <div className="form-row" style={{ alignItems: 'flex-start', marginTop: 24 }}>
        <CategoryForm title={primaryForm.id ? '编辑一级分类' : '新增一级分类'} form={primaryForm} onChange={updatePrimaryForm} onSubmit={submitPrimary} onCancel={() => setPrimaryForm(EMPTY_PRIMARY)} saving={saving} />
        <CategoryForm title={secondaryForm.id ? '编辑二级分类' : '新增二级分类'} form={secondaryForm} onChange={updateSecondaryForm} onSubmit={submitSecondary} onCancel={() => setSecondaryForm(EMPTY_SECONDARY)} saving={saving} primaryCategories={categories} disableParent={Boolean(secondaryForm.id)} onStartCreate={startSecondaryCreation} />
      </div>}
      <h3 style={{ marginTop: 32 }}>分类迁移待处理报告</h3><div style={{ overflowX: 'auto' }}><table className="data-table" style={{ width: '100%' }}><thead><tr><th>物料</th><th>原分类</th><th>待处理原因</th><th>状态</th>{!isReadOnly && <th>操作</th>}</tr></thead><tbody>{issues.length === 0 ? <tr><td colSpan={isReadOnly ? 4 : 5}>暂无待处理分类迁移记录</td></tr> : issues.map(issue => <tr key={issue.id}><td>{issue.material_name || `物料 #${issue.warehouse_asset_id}`}</td><td>{issue.original_category}</td><td>{issue.reason_detail}</td><td>{issue.status === 'OPEN' ? '待处理' : '已解决'}</td>{!isReadOnly && <td><button className="btn btn-primary" onClick={() => beginResolution(issue)}>选择有效组合并解决</button></td>}</tr>)}</tbody></table></div>
    </>}
    {resolvingIssue && <div className="modal-overlay" onClick={() => setResolvingIssue(null)}><div className="modal-content" onClick={event => event.stopPropagation()}><div className="modal-header"><h2>解决分类待处理项</h2><button className="close-btn" onClick={() => setResolvingIssue(null)}>&times;</button></div><form onSubmit={resolveIssue}><div className="modal-body"><p>物料：{resolvingIssue.material_name || `#${resolvingIssue.warehouse_asset_id}`}；原分类：{resolvingIssue.original_category}</p><div className="form-row"><div className="form-group"><label>一级分类 *</label><select value={resolution.primary_category_id} onChange={changeResolutionPrimary} required><option value="">选择一级分类</option>{categories.filter(category => category.is_active).map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></div><div className="form-group"><label>二级分类 *</label><select value={resolution.secondary_category_id} disabled={!resolution.primary_category_id} onChange={event => setResolution(current => ({ ...current, secondary_category_id: event.target.value }))} required><option value="">{resolution.primary_category_id ? '选择二级分类' : '请先选择一级分类'}</option>{resolutionSecondaryCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select></div></div><div className="form-group"><label>处理说明</label><textarea value={resolution.resolution_note} onChange={event => setResolution(current => ({ ...current, resolution_note: event.target.value }))} rows="3" /></div></div><div className="modal-footer"><button type="button" className="btn btn-secondary" onClick={() => setResolvingIssue(null)}>取消</button><button type="submit" className="btn btn-primary" disabled={saving}>{saving ? '处理中...' : '确认解决'}</button></div></form></div></div>}
  </div>
}

function CategoryForm({ title, form, onChange, onSubmit, onCancel, saving, primaryCategories, disableParent, onStartCreate }) {
  const isSecondary = Boolean(primaryCategories)
  const isEditing = Boolean(form.id)
  return <form onSubmit={onSubmit} className="detail-info-block" style={{ flex: 1 }}><div className="detail-section-label">{title}</div>
    {isSecondary && <div className="form-group"><label>所属一级分类 *</label><select name="primary_category_id" value={form.primary_category_id} onChange={onChange} disabled={disableParent} required><option value="">选择一级分类</option>{primaryCategories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select>{disableParent && <small>二级分类不能直接更换所属一级分类；如需调整，请新建二级分类并迁移引用。</small>}</div>}
    <div className="form-row"><div className="form-group"><label>代码 *</label><input name="code" value={form.code} onChange={onChange} required /></div><div className="form-group"><label>名称 *</label><input name="name" value={form.name} onChange={onChange} required /></div></div><div className="form-group"><label>排序 *</label><input type="number" min="0" name="sort_order" value={form.sort_order} onChange={onChange} required /></div>
    <div style={{ display: 'flex', gap: 8 }}><button className="btn btn-primary" disabled={saving} type="submit">{isEditing ? '保存修改' : '新增分类'}</button><button className="btn btn-secondary" type="button" onClick={isEditing ? onCancel : (isSecondary ? onStartCreate : onCancel)}>取消</button></div>
  </form>
}

export default WarehouseCategoryManagement
