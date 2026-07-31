import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { useAuth } from '../contexts/AuthContext'
import WarehouseAssetDetail from './WarehouseAssetDetail'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }))

const primaryCategories = [
  { id: 1, name: '网络与机房耗材' },
  { id: 2, name: 'IT工具与借用物品' },
]
const secondaryByPrimary = {
  1: [{ id: 11, name: '交换机' }],
  2: [{ id: 21, name: '网线钳' }],
}
const activeAsset = {
  id: 1,
  name: '核心交换机',
  primary_category_id: 1,
  primary_category_name: '网络与机房耗材',
  secondary_category_id: 11,
  secondary_category_name: '交换机',
  classification_status: 'ACTIVE',
  issue_policy: 'CONSUMABLE',
  available_quantity: 8,
  allocated_quantity: 1,
  low_stock_threshold: 3,
  location: 'A-01',
}

const configureApi = ({ asset = activeAsset, secondaryLoader, materialLoader, migrationIssues = [] } = {}) => {
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/warehouse/categories/primary')) return Promise.resolve({ data: primaryCategories })
    const secondaryMatch = url.match(/primary\/(\d+)\/secondary$/)
    if (secondaryMatch) return secondaryLoader ? secondaryLoader(secondaryMatch[1]) : Promise.resolve({ data: secondaryByPrimary[secondaryMatch[1]] || [] })
    if (url.endsWith(`/warehouse/materials/${asset.id}`)) return materialLoader ? materialLoader() : Promise.resolve({ data: asset })
    if (url.endsWith('/warehouse/category-migration-issues')) return Promise.resolve({ data: migrationIssues })
    return Promise.reject(new Error(`未处理的请求：${url}`))
  })
}

const formField = (labelText) => screen.getByText(labelText, { selector: 'label' }).parentElement.querySelector('input, select')

const renderDetail = async (asset = activeAsset, props = {}) => {
  render(<WarehouseAssetDetail asset={asset} onClose={vi.fn()} onRefresh={vi.fn()} {...props} />)
  await screen.findByRole('heading', { name: asset.name })
  await waitFor(() => expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(new RegExp(`/warehouse/materials/${asset.id}$`))))
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuth.mockReturnValue({ isReadOnly: false })
  configureApi()
})

afterEach(cleanup)

describe('WarehouseAssetDetail', () => {
  // Validates: Requirements 7.4, 7.6, 12.1
  it('在详情中分开显示一级分类和二级分类', async () => {
    await renderDetail()

    expect(screen.getByText('一级分类', { selector: '.detail-label' })).toBeTruthy()
    expect(screen.getByText('二级分类', { selector: '.detail-label' })).toBeTruthy()
    expect(screen.getByText('网络与机房耗材', { selector: '.detail-value' })).toBeTruthy()
    expect(screen.getByText('交换机', { selector: '.detail-value' })).toBeTruthy()
  })

  // Validates: Requirements 7.4, 7.5, 7.6, 12.1
  it('编辑时先回填一级分类，待二级分类加载后再回填子项', async () => {
    let resolveSecondary
    const delayedSecondary = new Promise(resolve => { resolveSecondary = resolve })
    configureApi({ secondaryLoader: () => delayedSecondary })
    await renderDetail()

    fireEvent.click(screen.getByRole('button', { name: '编辑物料' }))
    await screen.findByRole('heading', { name: '编辑仓储物料' })
    await waitFor(() => expect(formField('一级分类 *').value).toBe('1'))
    expect(formField('二级分类 *').value).toBe('')

    resolveSecondary({ data: secondaryByPrimary[1] })
    await waitFor(() => expect(formField('二级分类 *').value).toBe('11'))
  })

  // Validates: Requirements 7.4, 7.5, 12.1
  it('切换一级分类会清空已回填的二级分类', async () => {
    await renderDetail()
    fireEvent.click(screen.getByRole('button', { name: '编辑物料' }))
    await screen.findByRole('heading', { name: '编辑仓储物料' })
    await waitFor(() => expect(formField('二级分类 *').value).toBe('11'))

    fireEvent.change(formField('一级分类 *'), { target: { value: '2' } })
    expect(formField('二级分类 *').value).toBe('')
    await waitFor(() => expect(formField('二级分类 *').options[1].text).toBe('网线钳'))
  })

  // Validates: Requirements 7.8, 7.9, 12.1, 12.4, 12.5
  it('对待迁移物料展示原分类、原因和只读提示，并禁用编辑入口', async () => {
    const pendingAsset = {
      ...activeAsset,
      id: 2,
      name: '历史网卡',
      classification_status: 'PENDING_MIGRATION',
      legacy_category: '计算机设备',
    }
    configureApi({
      asset: pendingAsset,
      materialLoader: () => Promise.reject({ response: { data: { detail: '待迁移物料不可进入活动详情' } } }),
      migrationIssues: [{ warehouse_asset_id: 2, reason_code: 'UNMAPPED', reason_detail: '未找到有效分类映射' }],
    })
    await renderDetail(pendingAsset)

    expect(await screen.findByText('分类待处理')).toBeTruthy()
    expect(screen.getByText('计算机设备')).toBeTruthy()
    expect(screen.getByText('未找到有效分类映射')).toBeTruthy()
    expect(screen.getByText('该物料处于只读状态，请由有写权限的用户在分类目录维护中完成一级和二级分类映射。')).toBeTruthy()
    expect(screen.getByText('分类待处理记录不可编辑，请先在分类目录维护中解决。')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '编辑物料' })).toBeNull()
  })

  // Validates: Requirements 2.5, 7.4, 7.5, 12.1
  it('编辑仅保存仓储物料，不触发旧的扣库后建卡编排', async () => {
    axios.put.mockResolvedValue({ data: { ...activeAsset, name: '已更新交换机' } })
    const onRefresh = vi.fn()
    await renderDetail(activeAsset, { onRefresh })
    fireEvent.click(screen.getByRole('button', { name: '编辑物料' }))
    await screen.findByRole('heading', { name: '编辑仓储物料' })
    await waitFor(() => expect(formField('二级分类 *').value).toBe('11'))

    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(axios.put).toHaveBeenCalledWith(expect.stringMatching(/\/warehouse\/materials\/1$/), expect.objectContaining({
      primary_category_id: 1,
      secondary_category_id: 11,
      available_quantity: 8,
      allocated_quantity: 1,
      low_stock_threshold: 3,
    })))
    expect(axios.post).not.toHaveBeenCalled()
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
  })
})