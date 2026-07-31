import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { useAuth } from '../contexts/AuthContext'
import WarehouseCategoryManagement from './WarehouseCategoryManagement'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }))

const categories = [
  { id: 1, code: 'NETWORK', name: '网络与机房耗材', sort_order: 10, is_active: true, secondary_categories: [{ id: 11, primary_category_id: 1, code: 'SWITCH', name: '交换机', sort_order: 10, is_active: true }] },
  { id: 2, code: 'TOOLS', name: 'IT工具与借用物品', sort_order: 20, is_active: true, secondary_categories: [{ id: 21, primary_category_id: 2, code: 'CLAMP', name: '网线钳', sort_order: 10, is_active: true }] },
]
const openIssues = [{ id: 71, warehouse_asset_id: 91, material_name: '历史网卡', original_category: '计算机设备', reason_detail: '未找到有效分类映射', status: 'OPEN' }]

const configureApi = () => {
  let resolved = false
  axios.get.mockImplementation((url) => {
    if (url.endsWith('/warehouse/categories')) return Promise.resolve({ data: { categories } })
    if (url.endsWith('/warehouse/category-migration-issues')) return Promise.resolve({ data: resolved ? [] : openIssues })
    const match = url.match(/\/warehouse\/categories\/primary\/(\d+)\/secondary$/)
    if (match) return Promise.resolve({ data: categories.find(category => category.id === Number(match[1]))?.secondary_categories || [] })
    return Promise.reject(new Error(`未处理的请求：${url}`))
  })
  axios.patch.mockResolvedValue({ data: {} })
  axios.post.mockImplementation((url) => {
    if (url.endsWith('/warehouse/category-migration-issues/71/resolve')) resolved = true
    return Promise.resolve({ data: {} })
  })
}

const renderManagement = async () => {
  render(<WarehouseCategoryManagement />)
  await screen.findByText('网络与机房耗材', { selector: 'td' })
}
const categoryForm = title => screen.getByText(title, { selector: '.detail-section-label' }).closest('form')
const field = (form, label) => within(form).getByText(label, { selector: 'label' }).parentElement.querySelector('input, select, textarea')

beforeEach(() => {
  vi.clearAllMocks()
  useAuth.mockReturnValue({ isReadOnly: false })
  configureApi()
})
afterEach(cleanup)

describe('WarehouseCategoryManagement', () => {
  // Validates: Requirements 7.1–7.5, 12.1–12.3
  it('新增一级分类，并编辑二级分类的名称和排序而不允许直接换父级', async () => {
    await renderManagement()
    const primaryForm = categoryForm('新增一级分类')
    fireEvent.change(field(primaryForm, '代码 *'), { target: { value: 'OFFICE' } })
    fireEvent.change(field(primaryForm, '名称 *'), { target: { value: '办公与通用耗材' } })
    fireEvent.change(field(primaryForm, '排序 *'), { target: { value: '80' } })
    fireEvent.submit(primaryForm)
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/warehouse\/categories\/primary$/), { code: 'OFFICE', name: '办公与通用耗材', sort_order: 80 }))

    const secondaryTable = screen.getAllByRole('table')[1]
    fireEvent.click(within(within(secondaryTable).getByText('交换机', { selector: 'td' }).closest('tr')).getByRole('button', { name: '改名/排序' }))
    const secondaryForm = categoryForm('编辑二级分类')
    expect(field(secondaryForm, '所属一级分类 *').disabled).toBe(true)
    fireEvent.change(field(secondaryForm, '名称 *'), { target: { value: '核心交换机' } })
    fireEvent.change(field(secondaryForm, '排序 *'), { target: { value: '15' } })
    fireEvent.submit(secondaryForm)
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(expect.stringMatching(/\/warehouse\/categories\/secondary\/11$/), { code: 'SWITCH', name: '核心交换机', sort_order: 15 }))
  })

  // Validates: Requirements 7.2–7.5, 12.1–12.3
  it('通过启停接口更新目录状态', async () => {
    await renderManagement()
    const primaryTable = screen.getAllByRole('table')[0]
    fireEvent.click(within(within(primaryTable).getByText('网络与机房耗材', { selector: 'td' }).closest('tr')).getByRole('button', { name: '停用' }))
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(expect.stringMatching(/\/warehouse\/categories\/primary\/1$/), { is_active: false }))
  })

  // Validates: Requirements 7.2–7.5, 12.1–12.3
  it('在引用冲突时显示后端返回的中文错误提示', async () => {
    axios.patch.mockRejectedValueOnce({ response: { data: { detail: '该一级分类下仍存在启用的二级分类，不能停用' } } })
    await renderManagement()
    const primaryTable = screen.getAllByRole('table')[0]
    fireEvent.click(within(within(primaryTable).getByText('网络与机房耗材', { selector: 'td' }).closest('tr')).getByRole('button', { name: '停用' }))
    expect(await screen.findByText('该一级分类下仍存在启用的二级分类，不能停用')).toBeTruthy()
  })

  // Validates: Requirements 7.8, 7.9, 12.1–12.3
  it('展示待处理报告，并在选择有效组合解决后刷新报告', async () => {
    await renderManagement()
    expect(screen.getByText('分类迁移待处理报告')).toBeTruthy()
    expect(screen.getByText('历史网卡')).toBeTruthy()
    expect(screen.getByText('计算机设备')).toBeTruthy()
    expect(screen.getByText('未找到有效分类映射')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '选择有效组合并解决' }))
    const modal = screen.getByRole('heading', { name: '解决分类待处理项' }).closest('.modal-content')
    const [primary, secondary] = within(modal).getAllByRole('combobox')
    fireEvent.change(primary, { target: { value: '2' } })
    await waitFor(() => expect(secondary.options[1].text).toBe('网线钳'))
    fireEvent.change(secondary, { target: { value: '21' } })
    fireEvent.change(within(modal).getByRole('textbox'), { target: { value: '已人工确认' } })
    fireEvent.submit(within(modal).getByRole('button', { name: '确认解决' }).closest('form'))

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/warehouse\/category-migration-issues\/71\/resolve$/), { primary_category_id: 2, secondary_category_id: 21, resolution_note: '已人工确认' }))
    expect(await screen.findByText('暂无待处理分类迁移记录')).toBeTruthy()
    expect(axios.get.mock.calls.filter(([url]) => url.endsWith('/warehouse/category-migration-issues'))).toHaveLength(2)
  })

  // Validates: Requirements 12.1, 12.4, 12.5
  it('只读用户可查看分类和待处理报告，但不显示任何写控件', async () => {
    useAuth.mockReturnValue({ isReadOnly: true })
    await renderManagement()

    expect(screen.getByText('只读模式：可查看分类目录和待处理报告，不能维护分类或解决迁移问题。')).toBeTruthy()
    expect(screen.getByText('交换机', { selector: 'td' })).toBeTruthy()
    expect(screen.getByText('历史网卡')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '新增分类' })).toBeNull()
    expect(screen.queryByRole('button', { name: '改名/排序' })).toBeNull()
    expect(screen.queryByRole('button', { name: /停用|启用/ })).toBeNull()
    expect(screen.queryByRole('button', { name: '选择有效组合并解决' })).toBeNull()
    expect(screen.queryByRole('columnheader', { name: '维护' })).toBeNull()
    expect(screen.queryByRole('columnheader', { name: '操作' })).toBeNull()
  })
})