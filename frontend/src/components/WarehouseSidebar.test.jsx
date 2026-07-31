import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import WarehouseSidebar from './WarehouseSidebar'

vi.mock('axios', () => ({ default: { get: vi.fn() } }))

const primaryCategories = [{ id: 1, name: '网络与机房耗材' }, { id: 2, name: 'IT工具与借用物品' }]
const secondaryByPrimary = { 1: [{ id: 11, name: '交换机' }], 2: [{ id: 21, name: '网线钳' }] }

const configureApi = () => {
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/warehouse/categories/primary')) return Promise.resolve({ data: primaryCategories })
    const match = url.match(/primary\/(\d+)\/secondary$/)
    if (match) return Promise.resolve({ data: secondaryByPrimary[match[1]] || [] })
    if (url.endsWith('/warehouse/materials')) return Promise.resolve({ data: [] })
    return Promise.reject(new Error(`未处理的请求：${url}`))
  })
}

const renderSidebar = async () => {
  render(<WarehouseSidebar selectedAsset={null} onAssetSelect={vi.fn()} />)
  await screen.findByText('没有找到物料')
  await screen.findByRole('option', { name: '网络与机房耗材' })
}

beforeEach(() => { vi.clearAllMocks(); configureApi() })
afterEach(cleanup)

describe('WarehouseSidebar', () => {
  // Validates: Requirements 7.7, 12.1
  it('切换一级分类时清空已选择的二级分类', async () => {
    await renderSidebar()
    const [primary, secondary] = screen.getAllByRole('combobox')

    fireEvent.change(primary, { target: { value: '1' } })
    await waitFor(() => expect(secondary.options[1].text).toBe('交换机'))
    fireEvent.change(secondary, { target: { value: '11' } })
    expect(secondary.value).toBe('11')

    fireEvent.change(primary, { target: { value: '2' } })
    expect(secondary.value).toBe('')
    await waitFor(() => expect(secondary.options[1].text).toBe('网线钳'))
  })

  // Validates: Requirements 7.7, 12.1, 12.4
  it('将所有已指定的筛选条件同时作为 AND 查询参数提交', async () => {
    await renderSidebar()
    const [primary, secondary, lowStock] = screen.getAllByRole('combobox')

    fireEvent.change(primary, { target: { value: '1' } })
    await waitFor(() => expect(secondary.options[1].text).toBe('交换机'))
    fireEvent.change(secondary, { target: { value: '11' } })
    fireEvent.change(screen.getByPlaceholderText('物料名称'), { target: { value: '核心交换机' } })
    fireEvent.change(screen.getByPlaceholderText('可用数量（精确）'), { target: { value: '5' } })
    fireEvent.change(screen.getByPlaceholderText('已分配数量（精确）'), { target: { value: '2' } })
    fireEvent.change(screen.getByPlaceholderText('存放位置'), { target: { value: 'A-01' } })
    fireEvent.change(screen.getByPlaceholderText('低库存阈值（精确）'), { target: { value: '8' } })
    fireEvent.change(lowStock, { target: { value: 'true' } })

    await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith(expect.stringMatching(/\/warehouse\/materials$/), {
      params: { name: '核心交换机', primary_category_id: '1', secondary_category_id: '11', available_quantity: '5', allocated_quantity: '2', location: 'A-01', low_stock_threshold: '8', low_stock: 'true' },
    }))
  })
})