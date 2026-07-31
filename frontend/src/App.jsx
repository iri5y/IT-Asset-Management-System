import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import axios from 'axios'
import { AlertTriangle } from 'lucide-react'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Login from './components/Login'
import ChangePassword from './components/ChangePassword'
import UserMenu from './components/UserMenu'
import UserManagement from './components/UserManagement'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import AssetDetail from './components/AssetDetail'
import AssetModal from './components/AssetModal'
import ImportWizard from './components/ImportWizard'
import IdleAssets from './components/IdleAssets'
import Warehouse, { WarehouseModal } from './components/Warehouse'
import WarehouseSidebar from './components/WarehouseSidebar'
import WarehouseDashboard from './components/WarehouseDashboard'
import WarehouseAssetDetail from './components/WarehouseAssetDetail'
import ReturnManagement from './components/ReturnManagement'
import ReturnHistory from './components/ReturnHistory'
import ScanWorkstation from './components/ScanWorkstation'
import LocationManagement from './components/LocationManagement'
import BrandManagement from './components/BrandManagement'
import DepartmentManagement from './components/DepartmentManagement'
import RetiredAssets from './components/RetiredAssets'
import MaterialIssueManagement from './components/MaterialIssueManagement'
import ToolLoanManagement from './components/ToolLoanManagement'
import WarehouseCategoryManagement from './components/WarehouseCategoryManagement'

const API_URL = import.meta.env.VITE_API_URL || ''

// 受保护的路由组件
function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  
  if (loading) {
    return (
      <div className="app-loading">
        <div className="loading-spinner"></div>
        <p>加载中...</p>
      </div>
    )
  }
  
  if (!user) {
    return <Navigate to="/login" replace />
  }
  
  return children
}

// 管理员路由组件
function AdminRoute({ children }) {
  const { user, loading, isAdmin } = useAuth()
  
  if (loading) {
    return (
      <div className="app-loading">
        <div className="loading-spinner"></div>
        <p>加载中...</p>
      </div>
    )
  }
  
  if (!user) {
    return <Navigate to="/login" replace />
  }
  
  if (!isAdmin) {
    return <Navigate to="/" replace />
  }
  
  return children
}

// 写入入口路由组件：只读账号保留列表和详情读取，但不能进入纯业务写页面。
function WriteRoute({ children }) {
  const { user, loading, isReadOnly } = useAuth()

  if (loading) {
    return <div className="app-loading"><div className="loading-spinner"></div><p>加载中...</p></div>
  }
  if (!user) return <Navigate to="/login" replace />
  if (isReadOnly) return <Navigate to="/assets" replace />
  return children
}

// 登录页面包装
function LoginPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  
  useEffect(() => {
    if (user) {
      navigate('/', { replace: true })
    }
  }, [user, navigate])
  
  return <Login />
}

// 主应用内容
function MainApp() {
  const { user, passwordExpired, passwordRemind, mustChangePassword, isAdmin, isReadOnly, dismissPasswordRemind } = useAuth()
  const [showChangePassword, setShowChangePassword] = useState(false)
  const [showPasswordRemindBanner, setShowPasswordRemindBanner] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  
  const [assets, setAssets] = useState([])
  const [assetsLoading, setAssetsLoading] = useState(true)
  const [selectedAsset, setSelectedAsset] = useState(null)
  const [selectedWarehouseAsset, setSelectedWarehouseAsset] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [showWarehouseModal, setShowWarehouseModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [editingAsset, setEditingAsset] = useState(null)
  const [editingWarehouseAsset, setEditingWarehouseAsset] = useState(null)
  const [filters, setFilters] = useState({
    search: '',
    category: '',
    status: '',
    department: '',
    po_number: '',
    location: '',
  })

  // 根据路由确定当前tab
  const getActiveTab = () => {
    if (location.pathname === '/' || location.pathname === '/dashboard') return 'dashboard'
    if (location.pathname.startsWith('/warehouse')) return 'warehouse'
    if (location.pathname.startsWith('/returns')) return 'returns'
    if (location.pathname.startsWith('/scan')) return 'scan'
    if (location.pathname.startsWith('/material-issues')) return 'material-issues'
    if (location.pathname.startsWith('/tool-loans')) return 'tool-loans'
    if (location.pathname.startsWith('/fixed-assets/lifecycle')) return 'lifecycle'
    return 'assets'
  }
  
  const getWarehouseSubTab = () => {
    if (location.pathname === '/warehouse/management') return 'management'
    if (location.pathname === '/warehouse/categories') return 'categories'
    if (location.pathname === '/warehouse/idle') return 'idle'
    if (location.pathname === '/warehouse/retired') return 'retired'
    if (location.pathname === '/warehouse/locations') return 'locations'
    if (location.pathname === '/warehouse/asset-locations') return 'asset-locations'
    if (location.pathname === '/warehouse/brands') return 'brands'
    if (location.pathname === '/warehouse/departments') return 'departments'
    return 'dashboard'
  }

  const activeTab = getActiveTab()
  const warehouseSubTab = getWarehouseSubTab()

  // 处理URL参数中的筛选条件
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search)
    const statusParam = searchParams.get('status')
    const clearParam = searchParams.get('clear')
    
    if (location.pathname === '/assets') {
      if (clearParam === 'true') {
        // 清除所有筛选条件
        setFilters({
          search: '',
          category: '',
          status: '',
          department: '',
          po_number: '',
          location: '',
        })
      } else if (statusParam) {
        setFilters(prev => ({ ...prev, status: statusParam }))
      }
    }
  }, [location.search, location.pathname])

  useEffect(() => {
    if (user && !passwordExpired) {
      fetchAssets()
    }
  }, [filters, user, passwordExpired])

  useEffect(() => {
    const handleSwitchToIdleAssets = () => {
      navigate('/warehouse/idle')
      setSelectedWarehouseAsset(null)
    }
    
    const handleSelectAsset = (event) => {
      const { assetId } = event.detail
      console.log('Received selectAsset event for ID:', assetId)
      
      // 如果资产列表已加载，直接选择
      if (assets.length > 0) {
        const asset = assets.find(a => a.id === assetId)
        if (asset) {
          console.log('Found and selecting asset:', asset)
          setSelectedAsset(asset)
        } else {
          console.log('Asset not found in current list, will retry after fetch')
          // 如果没找到，可能是新创建的资产，需要重新获取列表
          fetchAssets().then(() => {
            // 重新获取后再次尝试选择
            setTimeout(() => {
              window.dispatchEvent(new CustomEvent('selectAssetRetry', { 
                detail: { assetId } 
              }))
            }, 100)
          })
        }
      } else {
        console.log('Assets not loaded yet, will retry after fetch')
        // 如果资产列表还没加载，等待加载完成后再选择
        fetchAssets().then(() => {
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('selectAssetRetry', { 
              detail: { assetId } 
            }))
          }, 100)
        })
      }
    }
    
    const handleSelectAssetRetry = (event) => {
      const { assetId } = event.detail
      console.log('Retrying selectAsset for ID:', assetId)
      
      const asset = assets.find(a => a.id === assetId)
      if (asset) {
        console.log('Found and selecting asset on retry:', asset)
        setSelectedAsset(asset)
      } else {
        console.log('Asset still not found after retry')
      }
    }
    
    window.addEventListener('switchToIdleAssets', handleSwitchToIdleAssets)
    window.addEventListener('selectAsset', handleSelectAsset)
    window.addEventListener('selectAssetRetry', handleSelectAssetRetry)
    
    return () => {
      window.removeEventListener('switchToIdleAssets', handleSwitchToIdleAssets)
      window.removeEventListener('selectAsset', handleSelectAsset)
      window.removeEventListener('selectAssetRetry', handleSelectAssetRetry)
    }
  }, [navigate, assets])

  useEffect(() => {
    if (passwordExpired) {
      setShowChangePassword(true)
    }
  }, [passwordExpired])

  useEffect(() => {
    if (passwordRemind && !passwordExpired) {
      setShowPasswordRemindBanner(true)
    }
  }, [passwordRemind, passwordExpired])

  const fetchAssets = async () => {
    try {
      setAssetsLoading(true)
      const params = {}
      Object.keys(filters).forEach(key => {
        if (filters[key]) params[key] = filters[key]
      })
      const response = await axios.get(`${API_URL}/assets/`, { params })
      setAssets(response.data)
      
      if (selectedAsset) {
        const updatedAsset = response.data.find(a => a.id === selectedAsset.id)
        if (updatedAsset) {
          setSelectedAsset(updatedAsset)
        } else {
          // 资产不在当前筛选结果中（比如状态变了），单独获取最新数据
          try {
            const singleResponse = await axios.get(`${API_URL}/assets/${selectedAsset.id}`)
            setSelectedAsset(singleResponse.data)
          } catch {
            // 资产可能已被删除
            setSelectedAsset(null)
          }
        }
      }
    } catch (error) {
      console.error('获取资产失败:', error)
      if (error.response?.status !== 401) {
        alert('获取资产失败，请检查后端服务是否运行')
      }
    } finally {
      setAssetsLoading(false)
    }
  }

  if (passwordExpired || mustChangePassword) {
    return (
      <ChangePassword
        required={true}
        onSuccess={() => setShowChangePassword(false)}
      />
    )
  }

  const handleAddAsset = () => {
    setEditingAsset(null)
    setShowModal(true)
  }

  const handleEditAsset = (asset) => {
    setEditingAsset(asset)
    setShowModal(true)
  }

  const handleSaveAsset = async (assetData) => {
    try {
      if (editingAsset) {
        await axios.put(`${API_URL}/assets/${editingAsset.id}`, assetData)
      } else {
        await axios.post(`${API_URL}/assets/`, assetData)
      }
      setShowModal(false)
      fetchAssets()
    } catch (error) {
      console.error('保存资产失败:', error)
      alert('保存资产失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  const handleSelectAsset = (asset) => {
    setSelectedAsset(asset)
  }

  const handleCloseDetail = () => {
    setSelectedAsset(null)
  }

  const handleSelectWarehouseAsset = (asset) => {
    setSelectedWarehouseAsset(asset)
    if (warehouseSubTab === 'dashboard') {
      navigate('/warehouse/management')
    }
  }

  const handleCloseWarehouseDetail = () => {
    setSelectedWarehouseAsset(null)
  }

  const handleEditWarehouseAsset = (asset) => {
    setEditingWarehouseAsset(asset)
    setShowWarehouseModal(true)
  }

  const handleDeleteWarehouseAsset = async (id) => {
    setSelectedWarehouseAsset(null)
  }

  const handleReturnAssetClick = (asset) => {
    navigate('/assets')
    setSelectedAsset(asset)
  }

  const handleSaveWarehouseAsset = async (assetData) => {
    try {
      if (editingWarehouseAsset) {
        await axios.put(`${API_URL}/warehouse/${editingWarehouseAsset.id}`, assetData)
      } else {
        await axios.post(`${API_URL}/warehouse/`, assetData)
      }
      setShowWarehouseModal(false)
      setEditingWarehouseAsset(null)
      if (selectedWarehouseAsset && editingWarehouseAsset && selectedWarehouseAsset.id === editingWarehouseAsset.id) {
        const response = await axios.get(`${API_URL}/warehouse/${editingWarehouseAsset.id}`)
        setSelectedWarehouseAsset(response.data)
      }
    } catch (error) {
      console.error('保存库房资产失败:', error)
      alert('保存库房资产失败: ' + (error.response?.data?.detail || error.message))
    }
  }

  return (
    <div className="app-container">
      <div className="app-header">
        <h1>IT资产管理系统</h1>
        <div className="nav-tabs main-tabs">
          <button 
            className={`nav-tab ${location.pathname === '/' || location.pathname === '/dashboard' ? 'active' : ''}`}
            onClick={() => {
              setFilters({ search: '', category: '', status: '', department: '', po_number: '', location: '' })
              navigate('/')
            }}
          >
            资产看板
          </button>
          <button 
            className={`nav-tab ${activeTab === 'assets' ? 'active' : ''}`}
            onClick={() => navigate('/assets')}
          >
            资产管理
          </button>
          <button
            className={`nav-tab ${activeTab === 'lifecycle' ? 'active' : ''}`}
            onClick={() => navigate('/fixed-assets/lifecycle')}
          >
            固定资产生命周期
          </button>
          <button 
            className={`nav-tab ${activeTab === 'warehouse' ? 'active' : ''}`}
            onClick={() => navigate('/warehouse')}
          >
            库房管理
          </button>
          <button 
            className={`nav-tab ${activeTab === 'returns' ? 'active' : ''}`}
            onClick={() => navigate('/returns')}
          >
            资产归还
          </button>
          <button
            className={`nav-tab ${activeTab === 'material-issues' ? 'active' : ''}`}
            onClick={() => navigate('/material-issues')}
          >
            低值领用与专业发放
          </button>
          <button
            className={`nav-tab ${activeTab === 'tool-loans' ? 'active' : ''}`}
            onClick={() => navigate('/tool-loans')}
          >
            工具借还
          </button>
          {!isReadOnly && <button
            className={`nav-tab ${activeTab === 'scan' ? 'active' : ''}`}
            onClick={() => navigate('/scan')}
          >
            扫码工作台
          </button>}
        </div>
        <UserMenu 
          onChangePassword={() => setShowChangePassword(true)}
          onManageUsers={() => navigate('/admin/users')}
        />
      </div>

      {showPasswordRemindBanner && (
        <div className="password-remind-banner">
          <span><AlertTriangle size={16} style={{ verticalAlign: 'middle', marginRight: 6 }} /> 您的密码已超过90天未修改，建议尽快修改密码以确保账号安全</span>
          <div className="banner-actions">
            <button 
              className="btn btn-sm btn-primary"
              onClick={() => {
                setShowPasswordRemindBanner(false)
                setShowChangePassword(true)
              }}
            >
              立即修改
            </button>
            <button 
              className="btn btn-sm btn-secondary"
              onClick={() => {
                setShowPasswordRemindBanner(false)
                dismissPasswordRemind()
              }}
            >
              稍后提醒
            </button>
          </div>
        </div>
      )}

      <div className="app-body">
        {activeTab === 'dashboard' ? (
          <div className="main-panel" style={{ width: '100%' }}>
            <Dashboard 
              assets={assets} 
              onGlobalSearch={(searchTerm) => {
                if (searchTerm.trim()) {
                  setFilters(prev => ({ ...prev, search: searchTerm }))
                  navigate('/assets')
                }
              }}
            />
          </div>
        ) : activeTab === 'lifecycle' ? (
          <div className="main-panel" style={{ width: '100%' }}>
            <FixedAssetLifecycle
              assets={assets}
              loading={assetsLoading}
              onRefresh={fetchAssets}
              isReadOnly={isReadOnly}
            />
          </div>
        ) : activeTab === 'assets' ? (
          <div className="main-panel" style={{ width: '100%', position: 'relative', padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <Sidebar
                assets={assets}
                selectedAsset={selectedAsset}
                onSelectAsset={handleSelectAsset}
                filters={filters}
                setFilters={setFilters}
                onImport={() => setShowImportModal(true)}
              />
              <div className="main-panel" style={{ flex: 1, overflow: 'auto' }}>
                {selectedAsset ? (
                  <AssetDetail
                    asset={selectedAsset}
                    onClose={handleCloseDetail}
                    onEdit={handleEditAsset}
                    onRefresh={fetchAssets}
                    isAdmin={isAdmin}
                  />
                ) : assetsLoading ? (
                  <div className="loading">加载中...</div>
                ) : (
                  <div className="empty-state">
                    <h3>选择一个资产查看详情</h3>
                    <p>从左侧列表中点击任意资产来查看详细信息</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : activeTab === 'warehouse' ? (
          selectedWarehouseAsset ? (
            <>
              <WarehouseSidebar 
                selectedAsset={selectedWarehouseAsset}
                onAssetSelect={handleSelectWarehouseAsset}
              />
              <div className="main-panel" style={{ flex: 1 }}>
                <WarehouseAssetDetail
                  asset={selectedWarehouseAsset}
                  onClose={handleCloseWarehouseDetail}
                  onEdit={handleEditWarehouseAsset}
                  onDelete={handleDeleteWarehouseAsset}
                  onRefresh={async () => {
                    // 刷新库房资产详情
                    try {
                      const response = await axios.get(`${API_URL}/warehouse/${selectedWarehouseAsset.id}`)
                      setSelectedWarehouseAsset(response.data)
                    } catch (error) {
                      console.error('刷新库房资产失败:', error)
                    }
                    // 同时刷新主资产列表（新分配的资产需要出现在资产管理中）
                    fetchAssets()
                  }}
                  onBackToHome={() => {
                    setSelectedWarehouseAsset(null)
                    navigate('/warehouse')
                  }}
                  isAdmin={isAdmin}
                />
              </div>
            </>
          ) : (
            <div className="main-panel" style={{ width: '100%' }}>
              <div className="warehouse-tabs">
                <div className="nav-tabs" style={{ marginBottom: '20px' }}>
                  <button 
                    className={`nav-tab ${warehouseSubTab === 'dashboard' ? 'active' : ''}`}
                    onClick={() => {
                      navigate('/warehouse')
                      setSelectedWarehouseAsset(null)
                    }}
                  >
                    库房看板
                  </button>
                  <button 
                    className={`nav-tab ${warehouseSubTab === 'management' ? 'active' : ''}`}
                    onClick={() => {
                      navigate('/warehouse/management')
                      setSelectedWarehouseAsset(null)
                    }}
                  >
                    库存管理
                  </button>
                  <button
                    className={`nav-tab ${warehouseSubTab === 'categories' ? 'active' : ''}`}
                    onClick={() => {
                      navigate('/warehouse/categories')
                      setSelectedWarehouseAsset(null)
                    }}
                  >
                    仓储目录与迁移
                  </button>
                  <button 
                    className={`nav-tab ${warehouseSubTab === 'idle' ? 'active' : ''}`}
                    onClick={() => {
                      navigate('/warehouse/idle')
                      setSelectedWarehouseAsset(null)
                    }}
                  >
                    库房闲置
                  </button>
                  <button
                    className={`nav-tab ${warehouseSubTab === 'retired' ? 'active' : ''}`}
                    onClick={() => {
                      navigate('/warehouse/retired')
                      setSelectedWarehouseAsset(null)
                    }}
                  >
                    报废资产
                  </button>
                  {isAdmin && (
                    <button 
                      className={`nav-tab ${warehouseSubTab === 'locations' ? 'active' : ''}`}
                      onClick={() => {
                        navigate('/warehouse/locations')
                        setSelectedWarehouseAsset(null)
                      }}
                    >
                      库房位置
                    </button>
                  )}
                  {isAdmin && (
                    <button 
                      className={`nav-tab ${warehouseSubTab === 'asset-locations' ? 'active' : ''}`}
                      onClick={() => {
                        navigate('/warehouse/asset-locations')
                        setSelectedWarehouseAsset(null)
                      }}
                    >
                      资产位置
                    </button>
                  )}
                  {isAdmin && (
                    <button 
                      className={`nav-tab ${warehouseSubTab === 'brands' ? 'active' : ''}`}
                      onClick={() => {
                        navigate('/warehouse/brands')
                        setSelectedWarehouseAsset(null)
                      }}
                    >
                      品牌管理
                    </button>
                  )}
                  {isAdmin && (
                    <button 
                      className={`nav-tab ${warehouseSubTab === 'departments' ? 'active' : ''}`}
                      onClick={() => {
                        navigate('/warehouse/departments')
                        setSelectedWarehouseAsset(null)
                      }}
                    >
                      部门管理
                    </button>
                  )}
                </div>
                {warehouseSubTab === 'dashboard' ? (
                  <WarehouseDashboard 
                    onAssetClick={handleSelectWarehouseAsset}
                  />
                ) : warehouseSubTab === 'management' ? (
                  <Warehouse 
                    selectedAsset={selectedWarehouseAsset}
                    onAssetSelect={handleSelectWarehouseAsset}
                  />
                ) : warehouseSubTab === 'categories' ? (
                  <WarehouseCategoryManagement />
                ) : warehouseSubTab === 'locations' ? (
                  <LocationManagement />
                ) : warehouseSubTab === 'retired' ? (
                  <RetiredAssets
                    onAssetSelect={(asset) => {
                      navigate('/assets')
                      setSelectedAsset(asset)
                    }}
                  />
                ) : warehouseSubTab === 'asset-locations' ? (
                  <LocationManagement type="office" />
                ) : warehouseSubTab === 'brands' ? (
                  <BrandManagement />
                ) : warehouseSubTab === 'departments' ? (
                  <DepartmentManagement />
                ) : (
                  <IdleAssets 
                    onAssetSelect={(asset) => {
                      navigate('/assets')
                      setSelectedAsset(asset)
                    }}
                    selectedAsset={selectedAsset}
                  />
                )}
              </div>
            </div>
          )
        ) : activeTab === 'scan' ? (
          <div className="main-panel" style={{ width: '100%' }}>
            <ScanWorkstation />
          </div>
        ) : activeTab === 'material-issues' ? (
          <div className="main-panel" style={{ width: '100%' }}>
            <MaterialIssueManagement />
          </div>
        ) : activeTab === 'tool-loans' ? (
          <div className="main-panel" style={{ width: '100%' }}>
            <ToolLoanManagement />
          </div>
        ) : (
          <div className="main-panel" style={{ width: '100%' }}>
            <ReturnManagement onAssetClick={handleReturnAssetClick} />
          </div>
        )}
      </div>

      {showModal && (
        <AssetModal
          asset={editingAsset}
          onClose={() => setShowModal(false)}
          onSave={handleSaveAsset}
        />
      )}

      {showWarehouseModal && (
        <WarehouseModal
          asset={editingWarehouseAsset}
          onClose={() => {
            setShowWarehouseModal(false)
            setEditingWarehouseAsset(null)
          }}
          onSave={handleSaveWarehouseAsset}
        />
      )}

      {showImportModal && (
        <ImportWizard
          onClose={() => setShowImportModal(false)}
          onImportSuccess={() => {
            fetchAssets()
          }}
        />
      )}

      {showChangePassword && !passwordExpired && (
        <ChangePassword
          required={false}
          onSuccess={() => setShowChangePassword(false)}
          onCancel={() => setShowChangePassword(false)}
        />
      )}
    </div>
  )
}

const FIXED_ASSET_CATEGORIES = new Set(['PC', 'NB', 'PD'])
const FIXED_ASSET_CATEGORY_NAMES = new Set(['台式机', '笔记本电脑', '平板电脑'])
const lifecycleNow = () => new Date().toISOString().slice(0, 16)

function FixedAssetLifecycle({ assets, loading, onRefresh, isReadOnly }) {
  const fixedAssets = assets.filter(asset => FIXED_ASSET_CATEGORIES.has(asset.asset_category_code) || FIXED_ASSET_CATEGORY_NAMES.has(asset.category))
  const [selectedId, setSelectedId] = useState(null)
  const [action, setAction] = useState(null)
  const [form, setForm] = useState({ recipient_name: '', recipient_employee_id: '', recipient_department: '', issued_at: lifecycleNow() })
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const selectedAsset = fixedAssets.find(asset => asset.id === selectedId) || null

  const beginAction = (nextAction) => {
    setError('')
    setMessage('')
    setAction(nextAction)
    setForm({
      recipient_name: nextAction === 'return' ? selectedAsset?.employee_name || '' : '',
      recipient_employee_id: nextAction === 'return' ? selectedAsset?.employee_id || '' : '',
      recipient_department: nextAction === 'return' ? selectedAsset?.department || '' : '',
      issued_at: lifecycleNow(),
    })
  }

  const submit = async event => {
    event.preventDefault()
    if (!selectedAsset || !action) return
    setError('')
    const endpoint = action === 'repair-complete' ? 'repair-complete' : action
    let payload
    if (action === 'repair') payload = undefined
    else if (action === 'return') payload = bindingPayload(form, false)
    else if (action === 'repair-complete') {
      const hasNewBinding = form.recipient_name || form.recipient_employee_id || form.recipient_department
      if (hasNewBinding && (!form.recipient_name || !form.recipient_employee_id || !form.recipient_department)) {
        setError('维修完成后如需重新发放，须完整填写领用人、工号和部门。')
        return
      }
      payload = hasNewBinding ? bindingPayload(form, true) : { recipient_name: null, recipient_employee_id: null, recipient_department: null, issued_at: null }
    } else payload = bindingPayload(form, true)

    try {
      setSubmitting(true)
      const response = payload === undefined
        ? await axios.post(`${API_URL}/fixed-assets/${selectedAsset.id}/${endpoint}`)
        : await axios.post(`${API_URL}/fixed-assets/${selectedAsset.id}/${endpoint}`, payload)
      setMessage(`${lifecycleActionLabel(action)}成功，审计编号：${response.data.audit_log_id}`)
      setAction(null)
      await onRefresh()
    } catch (requestError) {
      setError(requestError.response?.data?.detail || '固定资产生命周期操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  return <div className="warehouse-container">
    <div className="warehouse-header"><div><h2>固定资产生命周期</h2><p>仅展示经受控入库形成的台式机、笔记本电脑和平板电脑；发放、归还、转移和维修均通过受控接口执行。</p></div></div>
    {message && <div className="alert alert-success">{message}</div>}
    {error && <div className="alert alert-error">{error}</div>}
    {isReadOnly && <div className="alert alert-info">只读账号可查看固定资产列表与详情，不能执行生命周期写操作。</div>}
    {loading ? <div className="loading">加载中...</div> : <div className="form-row" style={{ alignItems: 'flex-start' }}>
      <div className="warehouse-by-location" style={{ flex: 1, maxHeight: 560, overflowY: 'auto' }}>
        {fixedAssets.length === 0 ? <div className="empty-state"><h3>暂无受控固定资产</h3><p>请通过扫码工作台完成受控入库。</p></div> : fixedAssets.map(asset => <button type="button" key={asset.id} className={`warehouse-grid-card ${selectedId === asset.id ? 'active' : ''}`} style={{ width: '100%', textAlign: 'left', cursor: 'pointer' }} onClick={() => { setSelectedId(asset.id); setAction(null); setError('') }}><div className="grid-card-header"><span className="grid-card-name">{asset.fixed_asset_number || asset.asset_tag}</span><span className={`status-badge status-${asset.status.replace(/\s+/g, '-')}`}>{asset.status}</span></div><div>{asset.category} · SN：{asset.serial_number || '-'}</div><div>使用人：{asset.employee_name || '闲置'}</div></button>)}
      </div>
      <div className="detail-info-block" style={{ flex: 2 }}>
        {!selectedAsset ? <div className="empty-state"><h3>选择固定资产查看详情</h3></div> : <><div className="detail-section-label">{selectedAsset.fixed_asset_number || selectedAsset.asset_tag} 生命周期详情</div><div className="detail-grid compact"><div className="detail-item"><div className="detail-label">品类</div><div className="detail-value">{selectedAsset.category}</div></div><div className="detail-item"><div className="detail-label">状态</div><div className="detail-value">{selectedAsset.status}</div></div><div className="detail-item"><div className="detail-label">序列号</div><div className="detail-value font-data">{selectedAsset.serial_number || '-'}</div></div><div className="detail-item"><div className="detail-label">领用人</div><div className="detail-value">{selectedAsset.employee_name || '-'}</div></div><div className="detail-item"><div className="detail-label">工号</div><div className="detail-value">{selectedAsset.employee_id || '-'}</div></div><div className="detail-item"><div className="detail-label">部门</div><div className="detail-value">{selectedAsset.department || '-'}</div></div></div>{!isReadOnly && <div className="action-buttons" style={{ marginTop: 20 }}>{selectedAsset.status === '闲置' && <button className="btn btn-primary" onClick={() => beginAction('issue')}>发放</button>}{selectedAsset.status === '使用中' && <><button className="btn btn-secondary" onClick={() => beginAction('return')}>归还</button><button className="btn btn-primary" onClick={() => beginAction('transfer')}>转移</button></>}{['闲置', '使用中'].includes(selectedAsset.status) && <button className="btn btn-secondary" onClick={() => beginAction('repair')}>送修</button>}{selectedAsset.status === '维修中' && <button className="btn btn-primary" onClick={() => beginAction('repair-complete')}>完成维修</button>}</div>}</>}
      </div>
    </div>}
    {action && selectedAsset && <div className="modal-overlay" onClick={() => !submitting && setAction(null)}><div className="modal-content" onClick={event => event.stopPropagation()}><div className="modal-header"><h2>{lifecycleActionLabel(action)}：{selectedAsset.fixed_asset_number || selectedAsset.asset_tag}</h2><button className="close-btn" disabled={submitting} onClick={() => setAction(null)}>&times;</button></div><form onSubmit={submit}><div className="modal-body">{action === 'repair' ? <p>确认送修后，资产将进入“维修中”状态并清除当前领用绑定。</p> : <LifecycleBindingFields form={form} setForm={setForm} action={action} />}{error && <div className="alert alert-error">{error}</div>}</div><div className="modal-footer"><button type="button" className="btn btn-secondary" disabled={submitting} onClick={() => setAction(null)}>取消</button><button type="submit" className="btn btn-primary" disabled={submitting}>{submitting ? '提交中...' : `确认${lifecycleActionLabel(action)}`}</button></div></form></div></div>}
  </div>
}

function LifecycleBindingFields({ form, setForm, action }) {
  const optionalBinding = action === 'repair-complete'
  const update = (field, value) => setForm(current => ({ ...current, [field]: value }))
  return <><p>{optionalBinding ? '不填写新领用绑定时，维修完成后资产将转为闲置；填写时必须完整。' : '请填写完整领用绑定信息。'}</p><div className="form-row"><div className="form-group"><label>领用人 {!optionalBinding && '*'}</label><input required={!optionalBinding} value={form.recipient_name} onChange={event => update('recipient_name', event.target.value)} /></div><div className="form-group"><label>工号 {!optionalBinding && '*'}</label><input required={!optionalBinding} value={form.recipient_employee_id} onChange={event => update('recipient_employee_id', event.target.value)} /></div></div><div className="form-row"><div className="form-group"><label>部门 {!optionalBinding && '*'}</label><input required={!optionalBinding} value={form.recipient_department} onChange={event => update('recipient_department', event.target.value)} /></div>{action !== 'return' && <div className="form-group"><label>发放日期和时间 *</label><input type="datetime-local" required value={form.issued_at} onChange={event => update('issued_at', event.target.value)} /></div>}</div></>
}

function bindingPayload(form, includeIssuedAt) {
  const payload = { recipient_name: form.recipient_name.trim(), recipient_employee_id: form.recipient_employee_id.trim(), recipient_department: form.recipient_department.trim() }
  return includeIssuedAt ? { ...payload, issued_at: new Date(form.issued_at).toISOString() } : payload
}

function lifecycleActionLabel(action) {
  return ({ issue: '发放', return: '归还', transfer: '转移', repair: '送修', 'repair-complete': '完成维修' })[action] || '操作'
}

// 用户管理页面包装
function UserManagementPage() {
  const navigate = useNavigate()
  return <UserManagement onClose={() => navigate(-1)} />
}

function ReturnHistoryPage() {
  const { isReadOnly } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const getActiveTab = () => {
    if (location.pathname.startsWith('/returns')) return 'returns'
    if (location.pathname.startsWith('/warehouse')) return 'warehouse'
    if (location.pathname === '/' || location.pathname === '/dashboard') return 'dashboard'
    return 'assets'
  }
  const activeTab = getActiveTab()

  return (
    <div className="app-container">
      <div className="app-header">
        <h1>IT资产管理系统</h1>
        <div className="nav-tabs main-tabs">
          <button className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => navigate('/')}>资产看板</button>
          <button className={`nav-tab ${activeTab === 'assets' ? 'active' : ''}`} onClick={() => navigate('/assets')}>资产管理</button>
          <button className={`nav-tab ${activeTab === 'warehouse' ? 'active' : ''}`} onClick={() => navigate('/warehouse')}>库房管理</button>
          <button className={`nav-tab ${activeTab === 'returns' ? 'active' : ''}`} onClick={() => navigate('/returns')}>资产归还</button>
          {!isReadOnly && <button className="nav-tab" onClick={() => navigate('/scan')}>扫码工作台</button>}
        </div>
        <UserMenu onChangePassword={() => {}} onManageUsers={() => navigate('/admin/users')} />
      </div>
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div className="main-panel" style={{ width: '100%' }}>
          <ReturnHistory />
        </div>
      </div>
    </div>
  )
}

function ScanPage() {
  const navigate = useNavigate()
  const location = useLocation()

  const getActiveTab = () => {
    if (location.pathname.startsWith('/scan')) return 'scan'
    if (location.pathname.startsWith('/returns')) return 'returns'
    if (location.pathname.startsWith('/warehouse')) return 'warehouse'
    if (location.pathname === '/' || location.pathname === '/dashboard') return 'dashboard'
    return 'assets'
  }
  const activeTab = getActiveTab()

  return (
    <div className="app-container">
      <div className="app-header">
        <h1>IT资产管理系统</h1>
        <div className="nav-tabs main-tabs">
          <button className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => navigate('/')}>资产看板</button>
          <button className={`nav-tab ${activeTab === 'assets' ? 'active' : ''}`} onClick={() => navigate('/assets')}>资产管理</button>
          <button className={`nav-tab ${activeTab === 'warehouse' ? 'active' : ''}`} onClick={() => navigate('/warehouse')}>库房管理</button>
          <button className={`nav-tab ${activeTab === 'returns' ? 'active' : ''}`} onClick={() => navigate('/returns')}>资产归还</button>
          <button className={`nav-tab ${activeTab === 'scan' ? 'active' : ''}`} onClick={() => navigate('/scan')}>扫码工作台</button>
        </div>
        <UserMenu onChangePassword={() => {}} onManageUsers={() => navigate('/admin/users')} />
      </div>
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div className="main-panel" style={{ width: '100%' }}>
          <ScanWorkstation />
        </div>
      </div>
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/admin/users" element={
            <AdminRoute>
              <UserManagementPage />
            </AdminRoute>
          } />
          <Route path="/" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/dashboard" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/assets" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/assets/all" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/fixed-assets/lifecycle" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/material-issues" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/tool-loans" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/warehouse" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/warehouse/management" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/warehouse/categories" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/warehouse/idle" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/warehouse/retired" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/warehouse/locations" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/warehouse/asset-locations" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/office/locations" element={
            <ProtectedRoute>
              <MainApp />
              </ProtectedRoute>
          } />
          <Route path="/warehouse/brands" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/warehouse/departments" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/returns" element={
            <ProtectedRoute>
              <MainApp />
            </ProtectedRoute>
          } />
          <Route path="/returns/history" element={
            <ProtectedRoute>
              <ReturnHistoryPage />
            </ProtectedRoute>
          } />
          <Route path="/scan" element={
            <WriteRoute>
              <MainApp />
            </WriteRoute>
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
