import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { useAuth } from '../contexts/AuthContext'
import Warehouse from './Warehouse'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }))

const primaryCategories = [{ id: 1, name: '网络与机房耗材' }, { id: 2, name: 'IT工具与借用物品' }]
const secondaryByPrimary = {
  1: [{ id: 11, name: '交换机' }],
  2: [{ id: 21, name: '网线钳' }],
}

const configureApi = ({ assets = [], secondaryLoader } = {}) => {
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/warehouse/categories/primary')) return Promise.resolve({ data: primaryCategories })
    const match = url.match(/primary\/(\d+)\/secondary$/)
    if (match) return secondaryLoader ? secondaryLoader(match[1]) : Promise.resolve({ data: secondaryByPrimary[match[1]] || [] })
    if (url.endsWith('/warehouse/materials')) return Promise.resolve({ data: assets })
    return Promise.reject(new Error(`未处理的请求：${url}`))
  })
}

const loadWarehouse = async (props = {}) => {
  render(<Warehouse {...props} />)
  await screen.findByText('没有符合条件的仓储物料')
}

const formField = (labelText) => screen.getByText(labelText, { selector: 'label' }).parentElement.querySelector('input, select')
const openAddForm = async () => {
  fireEvent.click(screen.getByRole('button', { name: /添加仓储物料/ }))
  await screen.findByRole('heading', { name: '添加仓储物料' })
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuth.mockReturnValue({ isReadOnly: false })
  configureApi()
})

afterEach(cleanup)

describe('Warehouse', () => {
  // Validates: Requirements 7.4, 7.5, 12.1
  it('新增表单在未选择一级分类时禁用二级分类', async () => {
    await loadWarehouse()
    await openAddForm()

    const secondary = formField('二级分类 *')
    expect(secondary.disabled).toBe(true)
    expect(secondary.options[0].text).toBe('请先选择一级分类')
  })

  // Validates: Requirements 7.4, 7.5, 12.1
  it('按所选一级分类加载对应的二级分类', async () => {
    await loadWarehouse()
    await openAddForm()

    fireEvent.change(formField('一级分类 *'), { target: { value: '1' } })
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith(expect.stringMatching(/\/warehouse\/categories\/primary\/1\/secondary$/)))
    await waitFor(() => expect(formField('二级分类 *').options[1].text).toBe('交换机'))

    expect(formField('二级分类 *').disabled).toBe(false)
    expect(formField('二级分类 *').options).toHaveLength(2)
  })

  // Validates: Requirements 7.4, 7.5, 12.1
  it('切换一级分类会立即清空已选择的二级分类', async () => {
    await loadWarehouse()
    await openAddForm()

    fireEvent.change(formField('一级分类 *'), { target: { value: '1' } })
    await waitFor(() => expect(formField('二级分类 *').options).toHaveLength(2))
    fireEvent.change(formField('二级分类 *'), { target: { value: '11' } })
    expect(formField('二级分类 *').value).toBe('11')

    fireEvent.change(formField('一级分类 *'), { target: { value: '2' } })
    expect(formField('二级分类 *').value).toBe('')
    await waitFor(() => expect(formField('二级分类 *').options[1].text).toBe('网线钳'))
  })

  // Validates: Requirements 7.4, 7.5, 12.1
  it('仅在有效的父子分类组合已选择时提交新物料', async () => {
    await loadWarehouse()
    await openAddForm()

    fireEvent.change(formField('物料名称 *'), { target: { value: '核心交换机' } })
    fireEvent.change(formField('一级分类 *'), { target: { value: '1' } })
    await waitFor(() => expect(formField('二级分类 *').options).toHaveLength(2))
    fireEvent.change(formField('二级分类 *'), { target: { value: '11' } })
    fireEvent.submit(formField('物料名称 *').closest('form'))

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/warehouse\/materials$/), expect.objectContaining({
      name: '核心交换机', primary_category_id: 1, secondary_category_id: 11,
    })))
  })

  // Validates: Requirements 7.4, 7.5, 7.6, 12.1
  it('编辑时先设置一级分类，待其二级分类加载完成后再回填二级分类', async () => {
    let resolveSecondary
    const delayedSecondary = new Promise(resolve => { resolveSecondary = resolve })
    configureApi({
      assets: [{ id: 9, name: '旧交换机', primary_category_id: 1, secondary_category_id: 11, available_quantity: 5, allocated_quantity: 0, low_stock_threshold: 2, low_stock: false }],
      secondaryLoader: () => delayedSecondary,
    })
    render(<Warehouse />)
    await screen.findByText('旧交换机')
    fireEvent.click(screen.getByRole('button', { name: '编辑' }))

    await waitFor(() => expect(formField('一级分类 *').value).toBe('1'))
    expect(formField('二级分类 *').value).toBe('')
    resolveSecondary({ data: secondaryByPrimary[1] })
    await waitFor(() => expect(formField('二级分类 *').value).toBe('11'))
  })

  // Validates: Requirements 7.6, 12.1
  it('在独立的一级和二级分类列中展示物料分类', async () => {
    configureApi({ assets: [{ id: 3, name: '千兆交换机', primary_category_name: '网络与机房耗材', secondary_category_name: '交换机', available_quantity: 8, allocated_quantity: 1, low_stock_threshold: 3, low_stock: false }] })
    render(<Warehouse />)
    await screen.findByText('千兆交换机')

    expect(screen.getByRole('columnheader', { name: '一级分类' })).toBeTruthy()
    expect(screen.getByRole('columnheader', { name: '二级分类' })).toBeTruthy()
    expect(screen.getByText('网络与机房耗材', { selector: 'td' })).toBeTruthy()
    expect(screen.getByText('交换机', { selector: 'td' })).toBeTruthy()
  })

  // Validates: Requirements 7.10, 7.11, 12.1
  it('仅对可用数量严格低于阈值的物料显示低库存预警', async () => {
    configureApi({ assets: [
      { id: 4, name: '阈值相等物料', primary_category_name: '网络与机房耗材', secondary_category_name: '交换机', available_quantity: 3, allocated_quantity: 0, low_stock_threshold: 3, low_stock: false },
      { id: 5, name: '低于阈值物料', primary_category_name: '网络与机房耗材', secondary_category_name: '交换机', available_quantity: 2, allocated_quantity: 0, low_stock_threshold: 3, low_stock: true },
    ] })
    render(<Warehouse />)
    await screen.findByText('阈值相等物料')

    expect(screen.getByText('库存正常')).toBeTruthy()
    expect(screen.getAllByText('低库存预警')).toHaveLength(1)
  })

  // Validates: Requirements 12.4, 12.5
  it('只读用户仍可查看仓储数据，但看不到物料写入控件', async () => {
    useAuth.mockReturnValue({ isReadOnly: true })
    configureApi({ assets: [{ id: 6, name: '只读物料', primary_category_name: 'IT工具与借用物品', secondary_category_name: '网线钳', available_quantity: 1, allocated_quantity: 0, low_stock_threshold: 0, low_stock: false }] })
    render(<Warehouse />)
    await screen.findByText('只读物料')

    expect(screen.queryByRole('button', { name: /添加仓储物料/ })).toBeNull()
    expect(screen.queryByRole('button', { name: '编辑' })).toBeNull()
    expect(screen.queryByRole('columnheader', { name: '操作' })).toBeNull()
    expect(screen.getByText('IT工具与借用物品', { selector: 'td' })).toBeTruthy()
  })
})