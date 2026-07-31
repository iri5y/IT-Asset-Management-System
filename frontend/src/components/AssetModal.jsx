import { useState, useEffect } from 'react'
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''

// 资产状况颜色配置
const CONDITION_STYLE = {
  '可用':   { bg: '#d1fae5', color: '#065f46', border: '#6ee7b7' },
  '损坏':   { bg: '#ffedd5', color: '#9a3412', border: '#fdba74' },
  '待报废': { bg: '#fee2e2', color: '#991b1b', border: '#fca5a5' },
}

function AssetModal({ asset, onClose, onSave, scanBanner }) {
  const isEditing = !!asset && !scanBanner  // 扫码预填时视为新建，不锁定品类

  const [formData, setFormData] = useState({
    asset_tag: '', category: '', brand: '', model: '', serial_number: '',
    hostname: '', mac_address: '', ip_address: '', system_version: '',
    antivirus_software: '', lock_number: '', supervisor: '',
    bios_password: false, tpm_status: false, has_desktop: false,
    employee_name: '', employee_id: '', department: '',
    status: '闲置', notes: '', location: '', po_number: '',
    condition: '可用',
  })
  const [brands, setBrands] = useState([])
  const [departments, setDepartments] = useState([])
  const [officelocations, setofficelocations] = useState([])

  // 记录原始状态，用于判断是否发生了状态变更
  const [originalStatus, setOriginalStatus] = useState('')

  useEffect(() => {
    axios.get(`${API_URL}/office-locations/`)
    .then(res => { setofficelocations(res.data) })
    .catch(err => { console.error("加载办公室位置失败：", err) })
  }, [])

  useEffect(() => {
    axios.get(`${API_URL}/brands/`).then(res => setBrands(res.data)).catch(() => {})
    axios.get(`${API_URL}/departments/flat`).then(res => setDepartments(res.data)).catch(() => {})
    if (asset) {
      setFormData({
        asset_tag: asset.asset_tag || '',
        category: asset.category || '',
        brand: asset.brand || '',
        model: asset.model || '',
        serial_number: asset.serial_number || '',
        hostname: asset.hostname || '',
        mac_address: asset.mac_address || '',
        ip_address: asset.ip_address || '',
        system_version: asset.system_version || '',
        antivirus_software: asset.antivirus_software || '',
        lock_number: asset.lock_number || '',
        supervisor: asset.supervisor || '',
        bios_password: asset.bios_password || false,
        tpm_status: asset.tpm_status || false,
        has_desktop: asset.has_desktop || false,
        employee_name: asset.employee_name || '',
        employee_id: asset.employee_id || '',
        department: asset.department || '',
        status: asset.status || '闲置',
        notes: asset.notes || '',
        location: asset.location || '',
        po_number: asset.po_number || '',
        condition: asset.condition || '可用',
      })
      setOriginalStatus(asset.status || '闲置')
    }
  }, [asset])

  const handleChange = (e) => {
    const { name, value } = e.target
    const upperCaseFields = ['mac_address', 'serial_number', 'system_version']
    const finalValue = upperCaseFields.includes(name) ? value.toUpperCase() : value

    // 状态切换为维修中时，自动将 condition 设为损坏，清空使用人
    if (name === 'status' && value === '维修中') {
      setFormData(prev => ({
        ...prev,
        status: '维修中',
        condition: '损坏',
        employee_name: '',
        employee_id: '',
        department: '',
      }))
      return
    }
    // 状态切换为闲置时，若 condition 未设置则默认可用
    if (name === 'status' && value === '闲置') {
      setFormData(prev => ({
        ...prev,
        status: '闲置',
        condition: prev.condition || '可用',
        notes: '',
      }))
      return
    }

    setFormData(prev => ({ ...prev, [name]: finalValue }))
  }

  // 状态变更为闲置时，损坏/待报废需要备注
  const needsConditionNote =
    formData.status === '闲置' &&
    (formData.condition === '损坏' || formData.condition === '待报废')

  // 状态变更为维修中时，备注必填
  const needsRepairNote = formData.status === '维修中'

  // 是否是状态发生了变更（编辑模式下）
  const statusChanged = isEditing && formData.status !== originalStatus

  const handleSubmit = (e) => {
    e.preventDefault()

    // 闲置 + 损坏/待报废 时备注必填
    if (needsConditionNote && !formData.notes.trim()) {
      alert('资产状况为「' + formData.condition + '」时，备注原因为必填项')
      return
    }
    // 维修中时备注必填
    if (needsRepairNote && !formData.notes.trim()) {
      alert('状态为「维修中」时，请填写维修备注（维修地点及损坏描述）')
      return
    }

    const finalData = { ...formData }
    if (!finalData.asset_tag) {
      finalData.asset_tag = `ZS-${new Date().getFullYear()}-${Date.now().toString().slice(-6)}`
    }

    const isDesktopSubmit = finalData.category === '台式机'
    const isLaptopSubmit = finalData.category === '笔记本电脑'
    const isComputerSubmit = isDesktopSubmit || isLaptopSubmit
    if (!isComputerSubmit) {
      delete finalData.ip_address
      delete finalData.system_version
      delete finalData.antivirus_software
      delete finalData.hostname
    }
    if (!isDesktopSubmit) {
      delete finalData.lock_number
    }
    if (!isLaptopSubmit) {
      delete finalData.bios_password
      delete finalData.tpm_status
      delete finalData.has_desktop
    }
    const isMobileSubmit = ['移动设备', '手机'].includes(finalData.category)
    if (!isComputerSubmit && !isMobileSubmit) {
      delete finalData.mac_address
    }

    if (!finalData.employee_name) finalData.employee_name = null
    if (!finalData.employee_id) finalData.employee_id = null
    if (!finalData.department) finalData.department = null

    onSave(finalData)
  }

  const isDesktop = formData.category === '台式机'
  const isLaptop = formData.category === '笔记本电脑'
  const isComputer = isDesktop || isLaptop
  const isMobile = ['移动设备', '手机'].includes(formData.category)

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" style={{ maxWidth: '580px' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{isEditing ? '编辑资产' : '添加资产'}</h2>
          <button className="close-btn" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body modal-body-scrollable">
            {/* 扫码工作台预填提示横幅 */}
            {scanBanner && (
              <div style={{
                background: '#EBF0F8', border: '1.5px solid #375B81', borderRadius: 6,
                padding: '10px 14px', marginBottom: 16,
                display: 'flex', alignItems: 'center', gap: 8,
                fontSize: 13, color: '#375B81', fontWeight: 500,
              }}>
                <span style={{ fontSize: 18 }}>🔍</span>
                {scanBanner}
              </div>
            )}

            {/* 资产编号 */}
            {(scanBanner || isEditing) && (
              <div className="form-group">
                <label>资产编号 {scanBanner && <span style={{ color: '#375B81', fontSize: 11 }}>（已自动生成，可修改）</span>}</label>
                <input
                  type="text"
                  name="asset_tag"
                  value={formData.asset_tag}
                  onChange={handleChange}
                  placeholder="ZS-XXXX-NNNNNN"
                  disabled={isEditing && !scanBanner}
                  style={isEditing && !scanBanner ? { opacity: 0.6, cursor: 'not-allowed' } : {}}
                />
              </div>
            )}

            {/* 品类 */}
            <div className="form-group">
              <label>品类 {!isEditing && '*'}</label>
              {isEditing ? (
                <input type="text" value={formData.category} disabled style={{ opacity: 0.6, cursor: 'not-allowed' }} />
              ) : (
                <select name="category" value={formData.category} onChange={handleChange} required>
                  <option value="">选择品类</option>
                  <option value="台式机">台式机</option>
                  <option value="笔记本电脑">笔记本电脑</option>
                  <option value="移动设备">移动设备</option>
                  <option value="手机">手机</option>
                  <option value="无线鼠标">无线鼠标</option>
                  <option value="显示器">显示器</option>
                  <option value="打印机">打印机</option>
                  <option value="网络设备">网络设备</option>
                  <option value="其他设备">其他设备</option>
                </select>
              )}
            </div>

            {/* 资产名 */}
            {isComputer && (
              <div className="form-group">
                <label>资产名</label>
                <input type="text" name="hostname" value={formData.hostname} onChange={handleChange} placeholder="例: IT001, FIN002" />
              </div>
            )}

            {/* 品牌、型号、序列号 */}
            <div className="form-row">
              <div className="form-group">
                <label>品牌</label>
                <select name="brand" value={formData.brand} onChange={handleChange}>
                  <option value="">选择品牌</option>
                  {brands.map(b => <option key={b.id} value={b.name}>{b.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>型号</label>
                <input type="text" name="model" value={formData.model} onChange={handleChange} placeholder="例: OptiPlex 7090" />
              </div>
            </div>
            <div className="form-group">
              <label>序列号</label>
              <input type="text" name="serial_number" value={formData.serial_number} onChange={handleChange} placeholder="设备序列号" style={{ textTransform: 'uppercase' }} />
            </div>

            {/* ===== 台式机专用 ===== */}
            {isDesktop && (<>
              <div className="form-row">
                <div className="form-group">
                  <label>资产位置 <span className="text-red-500">*</span></label>
                  <select
                    name='location'
                    value={formData.location || ''}
                    onChange={handleChange}
                    required={formData.category === '台式机'}
                  >
                    <option value="" disabled>请选择资产位置</option>
                    {Array.isArray(officelocations) && officelocations.map((loc) => (
                      <option key={loc.id} value={loc.name}>{loc.name}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>MAC地址</label>
                  <input type="text" name="mac_address" value={formData.mac_address} onChange={handleChange} placeholder="AA:BB:CC:DD:EE:FF" style={{ textTransform: 'uppercase' }} />
                </div>
                <div className="form-group">
                  <label>IP地址</label>
                  <input type="text" name="ip_address" value={formData.ip_address} onChange={handleChange} placeholder="192.168.1.100" />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>锁号</label>
                  <input type="text" name="lock_number" value={formData.lock_number} onChange={handleChange} />
                </div>
                <div className="form-group">
                  <label>系统版本</label>
                  <input type="text" name="system_version" value={formData.system_version} onChange={handleChange} placeholder="Windows 11 Pro" style={{ textTransform: 'uppercase' }} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>杀毒软件</label>
                  <input type="text" name="antivirus_software" value={formData.antivirus_software} onChange={handleChange} />
                </div>
                <div className="form-group">
                  <label>直属领导</label>
                  <input type="text" name="supervisor" value={formData.supervisor} onChange={handleChange} />
                </div>
              </div>
            </>)}

            {/* ===== 笔记本专用 ===== */}
            {isLaptop && (<>
              <div className="form-row">
                <div className="form-group">
                  <label>MAC地址</label>
                  <input type="text" name="mac_address" value={formData.mac_address} onChange={handleChange} placeholder="AA:BB:CC:DD:EE:FF" style={{ textTransform: 'uppercase' }} />
                </div>
                <div className="form-group">
                  <label>IP地址</label>
                  <input type="text" name="ip_address" value={formData.ip_address} onChange={handleChange} placeholder="192.168.1.100" />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>系统版本</label>
                  <input type="text" name="system_version" value={formData.system_version} onChange={handleChange} placeholder="Windows 11 Pro" style={{ textTransform: 'uppercase' }} />
                </div>
                <div className="form-group">
                  <label>杀毒软件</label>
                  <input type="text" name="antivirus_software" value={formData.antivirus_software} onChange={handleChange} />
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px' }}>
                <div className="toggle-row">
                  <span className="detail-label">BIOS密码</span>
                  <div className={`toggle-switch ${formData.bios_password ? 'active' : ''}`} onClick={() => setFormData({...formData, bios_password: !formData.bios_password})} />
                </div>
                <div className="toggle-row">
                  <span className="detail-label">TPM状态</span>
                  <div className={`toggle-switch ${formData.tpm_status ? 'active' : ''}`} onClick={() => setFormData({...formData, tpm_status: !formData.tpm_status})} />
                </div>
                <div className="toggle-row">
                  <span className="detail-label">是否有台式机</span>
                  <div className={`toggle-switch ${formData.has_desktop ? 'active' : ''}`} onClick={() => setFormData({...formData, has_desktop: !formData.has_desktop})} />
                </div>
              </div>
              <div className="form-group">
                <label>直属领导</label>
                <input type="text" name="supervisor" value={formData.supervisor} onChange={handleChange} />
              </div>
            </>)}

            {/* PO号（台式机和笔记本） */}
            {(isDesktop || formData.category === '笔记本电脑') && (
              <div className='form-row'>
                <div className='form-group'>
                  <label>PO号 <span className='text-red-500'>*</span></label>
                  <input
                    type='text'
                    name='po_number'
                    value={formData.po_number || ''}
                    onChange={handleChange}
                    required={isDesktop || formData.category === '笔记本电脑'}
                    placeholder='请输入纯数字PO号，例如：12000327'
                    pattern='^\d+$'
                    title='PO号必须为纯数字'
                  />
                </div>
              </div>
            )}

            {/* 移动设备专用 */}
            {isMobile && (
              <div className="form-row">
                <div className="form-group">
                  <label>资产位置</label>
                  <select
                    name='location'
                    value={formData.location || ''}
                    onChange={handleChange}
                  >
                    <option value="">请选择资产位置（可选）</option>
                    {Array.isArray(officelocations) && officelocations.map((loc) => (
                      <option key={loc.id} value={loc.name}>{loc.name}</option>
                    ))}
                </select>
              </div>
              <div className="form-group">
                <label>MAC地址</label>
                <input type="text" name="mac_address" value={formData.mac_address} onChange={handleChange} placeholder="AA:BB:CC:DD:EE:FF" style={{ textTransform: 'uppercase' }} />
              </div>
             </div>
            )}

            {/* 使用人信息（维修中时隐藏，因为自动清空） */}
            {formData.status !== '维修中' && (
              <>
                <div className="form-row">
                  <div className="form-group">
                    <label>使用人</label>
                    <input type="text" name="employee_name" value={formData.employee_name} onChange={handleChange} placeholder="员工姓名" />
                  </div>
                  <div className="form-group">
                    <label>工号</label>
                    <input type="text" name="employee_id" value={formData.employee_id} onChange={handleChange} placeholder="员工工号" />
                  </div>
                </div>
                <div className="form-group">
                  <label>部门</label>
                  <select name="department" value={formData.department} onChange={handleChange}>
                    <option value="">选择部门</option>
                    {departments.map(d => <option key={d.id} value={d.display}>{d.display}</option>)}
                  </select>
                </div>
              </>
            )}

            {/* ===== 状态 ===== */}
            <div className="form-group">
              <label>状态 *</label>
              <select name="status" value={formData.status} onChange={handleChange} required>
                <option value="闲置">闲置</option>
                <option value="使用中">使用中</option>
                <option value="维修中">维修中</option>
                <option value="报废">报废</option>
              </select>
            </div>

            {/* ===== 状态为「闲置」时：选择资产状况 ===== */}
            {formData.status === '闲置' && (
              <div className="form-group">
                <label>
                  资产状况 *
                  <span style={{ fontSize: 12, color: 'var(--color-muted)', marginLeft: 6, fontWeight: 400 }}>
                    （损坏或待报废时备注必填）
                  </span>
                </label>
                <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
                  {['可用', '损坏', '待报废'].map(cond => {
                    const cfg = CONDITION_STYLE[cond]
                    const selected = formData.condition === cond
                    return (
                      <button
                        key={cond}
                        type="button"
                        onClick={() => setFormData(prev => ({ ...prev, condition: cond, notes: '' }))}
                        style={{
                          padding: '6px 16px',
                          borderRadius: 6,
                          border: `2px solid ${selected ? cfg.border : 'var(--color-border)'}`,
                          background: selected ? cfg.bg : '#fff',
                          color: selected ? cfg.color : 'var(--color-body)',
                          fontWeight: selected ? 700 : 400,
                          fontSize: 13,
                          cursor: 'pointer',
                          transition: 'all 0.15s',
                        }}
                      >
                        {cond}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* ===== 状态为「维修中」时：提示信息 ===== */}
            {formData.status === '维修中' && (
              <div style={{
                background: '#fff7ed',
                border: '1px solid #fdba74',
                borderRadius: 6,
                padding: '10px 14px',
                fontSize: 13,
                color: '#9a3412',
                marginBottom: 4,
              }}>
                ⚠️ 状态变更为「维修中」后，资产将自动入库到库房闲置，使用人信息将被清除，资产状况将标记为「损坏」
              </div>
            )}

            {/* ===== 备注（闲置+损坏/待报废 或 维修中 时必填，其他时可选）===== */}
            <div className="form-group">
              <label>
                备注
                {(needsConditionNote || needsRepairNote) && (
                  <span style={{ color: '#e05252', marginLeft: 4 }}>*</span>
                )}
              </label>
              <textarea
                name="notes"
                value={formData.notes}
                onChange={handleChange}
                rows="3"
                placeholder={
                  needsRepairNote
                    ? '请填写维修地点及损坏描述（必填）'
                    : needsConditionNote
                    ? `请填写资产状况为「${formData.condition}」的原因（必填）`
                    : '可选备注'
                }
                required={needsConditionNote || needsRepairNote}
              />
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" className="btn btn-secondary" onClick={onClose}>取消</button>
            <button type="submit" className="btn btn-primary">保存资产</button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AssetModal
