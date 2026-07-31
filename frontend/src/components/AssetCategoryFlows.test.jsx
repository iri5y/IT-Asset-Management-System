import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { useAuth } from '../contexts/AuthContext'
import ScanWorkstation from './ScanWorkstation'
import Warehouse from './Warehouse'
import MaterialIssueManagement from './MaterialIssueManagement'
import ToolLoanManagement from './ToolLoanManagement'
import App from '../App'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('../contexts/AuthContext', () => ({
  AuthProvider: ({ children }) => children,
  useAuth: vi.fn(),
}))

const materials = [
  { id: 10, name: '笔记本终端库存', primary_category_code: 'TERMINAL_EQUIPMENT', available_quantity: 5, allocated_quantity: 0 },
  { id: 11, name: '无线鼠标', primary_category_code: 'INPUT_OFFICE_PERIPHERALS', available_quantity: 20, allocated_quantity: 0, issue_policy: 'CONSUMABLE' },
  { id: 12, name: '维修硬盘', primary_category_code: 'STORAGE_REPAIR_PARTS', available_quantity: 8, allocated_quantity: 0 },
  { id: 13, name: '网线', primary_category_code: 'NETWORK_SERVER_ROOM_CONSUMABLES', available_quantity: 30, allocated_quantity: 0 },
  { id: 14, name: '打印纸', primary_category_code: 'OFFICE_GENERAL_CONSUMABLES', available_quantity: 50, allocated_quantity: 0 },
  { id: 15, name: '光纤测试仪', primary_category_code: 'IT_TOOLS_LOAN_ITEMS', available_quantity: 2, allocated_quantity: 0 },
]

const field = label => screen.getByText(label, { selector: 'label' }).parentElement.querySelector('input, select')
const writableAuth = () => ({ user: { id: 1, username: '管理员', role: 'admin' }, loading: false, passwordExpired: false, passwordRemind: false, mustChangePassword: false, isAdmin: true, isReadOnly: false, dismissPasswordRemind: vi.fn() })

function configureGet() {
  axios.get.mockImplementation(url => {
    if (url.endsWith('/warehouse/categories/primary')) return Promise.resolve({ data: [{ id: 1, name: '输入与办公外设' }] })
    if (url.endsWith('/warehouse/categories/primary/1/secondary')) return Promise.resolve({ data: [{ id: 101, name: '鼠标' }] })
    if (url.endsWith('/warehouse/materials')) return Promise.resolve({ data: materials })
    if (url.endsWith('/departments/flat')) return Promise.resolve({ data: [{ id: 8, name: '网络部' }] })
    if (url.endsWith('/assets/')) return Promise.resolve({ data: [] })
    if (url.endsWith('/tool-loans')) return Promise.resolve({ data: [] })
    return Promise.resolve({ data: [] })
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuth.mockReturnValue(writableAuth())
  configureGet()
})

afterEach(() => {
  cleanup()
  window.history.pushState({}, '', '/')
})

describe('资产分类跨页面流程', () => {
  // Validates: Requirements 1.3, 12.1
  it('受控入库仅提供三类固定资产，并显示中文成功和错误提示', async () => {
    axios.post.mockResolvedValueOnce({ data: { asset: { fixed_asset_number: 'ZS-NB26-000001' } } })
    render(<ScanWorkstation />)
    await screen.findByText('固定资产受控入库')

    const category = field('固定资产品类 *')
    expect([...category.options].map(option => option.text)).toEqual(['台式机', '笔记本电脑', '平板电脑'])
    expect(screen.queryByRole('option', { name: '手机' })).toBeNull()
    fireEvent.change(field('终端设备库存 *'), { target: { value: '10' } })
    fireEvent.change(field('资产编号 *'), { target: { value: 'ZS-NB26-000001' } })
    fireEvent.change(field('序列号（SN）*'), { target: { value: 'SN-001' } })
    fireEvent.click(screen.getByRole('button', { name: '提交单件受控入库' }))

    await screen.findByText('资产 ZS-NB26-000001 已受控入库，当前状态为闲置。')
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/fixed-assets\/inbound$/), expect.objectContaining({ asset_category_code: 'NB', terminal_inventory_id: 10, serial_number: 'SN-001' }))
    axios.post.mockRejectedValueOnce({ response: { data: { detail: '资产编号已存在，请重新填写' } } })
    fireEvent.change(field('资产编号 *'), { target: { value: 'ZS-NB26-000002' } })
    fireEvent.change(field('序列号（SN）*'), { target: { value: 'SN-002' } })
    fireEvent.click(screen.getByRole('button', { name: '提交单件受控入库' }))
    expect(await screen.findByText('资产编号已存在，请重新填写')).toBeTruthy()
  })

  // Validates: Requirements 2.5, 5.2, 12.1
  it('仓储入口按数量保存非固定物料，不要求序列号且不调用建卡接口', async () => {
    axios.post.mockResolvedValue({ data: { id: 91 } })
    render(<Warehouse />)
    await screen.findByText('仓储物料管理')
    expect(screen.getByText('库房入口仅管理按数量入库的物料，不会创建台式机、笔记本电脑或平板电脑固定资产卡。')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /添加仓储物料/ }))
    await waitFor(() => expect(field('一级分类 *').options).toHaveLength(2))
    fireEvent.change(field('物料名称 *'), { target: { value: '无线鼠标' } })
    fireEvent.change(field('一级分类 *'), { target: { value: '1' } })
    await waitFor(() => expect(field('二级分类 *').options[1].text).toBe('鼠标'))
    fireEvent.change(field('二级分类 *'), { target: { value: '101' } })
    fireEvent.submit(field('物料名称 *').closest('form'))

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/warehouse\/materials$/), expect.objectContaining({ name: '无线鼠标', primary_category_id: 1, secondary_category_id: 101 })))
    expect(axios.post).toHaveBeenCalledTimes(1)
    expect(screen.queryByText(/序列号（SN）/)).toBeNull()
  })

  // Validates: Requirements 6.3, 12.1
  it('低值物料可在所有补充领用字段为空时成功发放并显示中文结果', async () => {
    axios.post.mockResolvedValueOnce({ data: { audit_log_id: 301, material_issue: { id: 71, quantity: 1, unreturned_quantity: 0, record_type: 'CONSUMABLE', issue_policy: 'CONSUMABLE', consumed_completed: true }, inventory: { name: '无线鼠标' } } })
    render(<MaterialIssueManagement />)
    await screen.findByText('物料发放管理')

    expect(screen.getByText('领用人（选填）')).toBeTruthy()
    expect(screen.getByText('工号（选填）')).toBeTruthy()
    expect(screen.getByText('部门（选填）')).toBeTruthy()
    expect(screen.getByText('用途（选填）')).toBeTruthy()
    fireEvent.change(field('低值物料 *'), { target: { value: '11' } })
    fireEvent.submit(field('低值物料 *').closest('form'))

    await screen.findByText('发放成功，审计编号：301')
    expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/material-issues$/), expect.objectContaining({ warehouse_asset_id: 11, quantity: 1, recipient_name: null, recipient_employee_id: null, recipient_department: null, purpose: null }))
  })

  // Validates: Requirements 8.1, 8.2, 8.3, 8.4, 9.1, 9.2, 9.3, 11.1, 11.2, 11.3, 12.1
  it('专业物料页面提交维修、网络和办公表单，并显示网络中文校验提示', async () => {
    axios.post.mockResolvedValueOnce({ data: { audit_log_id: 401 } }).mockResolvedValueOnce({ data: { audit_log_id: 402 } }).mockResolvedValueOnce({ data: { audit_log_id: 403 } })
    render(<MaterialIssueManagement />)
    await screen.findByText('物料发放管理')

    fireEvent.click(screen.getByRole('button', { name: '维修备件发放' }))
    fireEvent.change(field('维修备件发放物料 *'), { target: { value: '12' } })
    fireEvent.change(field('维修单号（与维修对象至少填写一项）'), { target: { value: 'REPAIR-9' } })
    fireEvent.change(field('硬盘序列号（硬盘备件可选）'), { target: { value: 'DISK-SN-9' } })
    fireEvent.submit(field('维修备件发放物料 *').closest('form'))
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/repair-parts\/issues$/), expect.objectContaining({ warehouse_asset_id: 12, repair_order_ref: 'REPAIR-9', disk_serial_number: 'DISK-SN-9' })))

    fireEvent.click(screen.getByRole('button', { name: '网络与机房耗材发放' }))
    expect(screen.getByText('网络用途可不填写；如填写任一用途，系统会校验至少一个有效关联。')).toBeTruthy()
    fireEvent.change(field('项目'), { target: { value: ' ' } })
    fireEvent.submit(field('网络与机房耗材发放物料 *').closest('form'))
    expect(await screen.findByText('填写网络用途时，必须提供有效部门、项目、机房或工单关联')).toBeTruthy()
    fireEvent.change(field('网络与机房耗材发放物料 *'), { target: { value: '13' } })
    fireEvent.change(field('项目'), { target: { value: '机房扩容' } })
    fireEvent.submit(field('网络与机房耗材发放物料 *').closest('form'))
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/network-consumables\/issues$/), expect.objectContaining({ warehouse_asset_id: 13, project_ref: '机房扩容' })))

    fireEvent.click(screen.getByRole('button', { name: '办公与通用耗材发放' }))
    expect(screen.getByText('领用策略：一次性消耗品。')).toBeTruthy()
    fireEvent.change(field('办公与通用耗材发放物料 *'), { target: { value: '14' } })
    fireEvent.submit(field('办公与通用耗材发放物料 *').closest('form'))
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/office-consumables\/issues$/), expect.objectContaining({ warehouse_asset_id: 14, quantity: 1 })))
    expect(await screen.findByText('发放成功，审计编号：403')).toBeTruthy()
  })

  // Validates: Requirements 10.1, 10.2, 10.6, 12.1
  it('工具借出提交必填数据和可选工具编号', async () => {
    axios.post.mockResolvedValueOnce({ data: { audit_log_id: 501 } })
    render(<ToolLoanManagement />)
    await screen.findByText('IT工具借还管理')
    fireEvent.click(screen.getByRole('button', { name: /借出工具/ }))
    await screen.findByRole('heading', { name: '借出IT工具' })
    fireEvent.change(field('IT工具物料 *'), { target: { value: '15' } })
    fireEvent.change(field('借用人 *'), { target: { value: '张三' } })
    fireEvent.change(field('借用数量 *'), { target: { value: '1' } })
    fireEvent.change(field('预计归还时间 *'), { target: { value: '2026-12-31T18:00' } })
    fireEvent.change(field('工具编号/二维码（贵重工具可选）'), { target: { value: 'QR-TOOL-15' } })
    fireEvent.submit(field('IT工具物料 *').closest('form'))

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringMatching(/\/tool-loans$/), expect.objectContaining({ warehouse_asset_id: 15, borrower_ref: '张三', quantity: 1, tool_identifier: 'QR-TOOL-15' })))
  })

  // Validates: Requirements 12.4, 12.5
  it('只读用户可在低值和工具记录页面间导航，但没有受控入库和写入入口', async () => {
    useAuth.mockReturnValue({ ...writableAuth(), user: { id: 2, username: '只读用户', role: 'readonly' }, isAdmin: false, isReadOnly: true })
    window.history.pushState({}, '', '/material-issues')
    render(<App />)

    await screen.findByText('只读账号：仅可查看库存，写入操作需写权限')
    expect(screen.getByRole('button', { name: '低值领用与专业发放' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '工具借还' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '扫码工作台' })).toBeNull()
    expect(screen.queryByRole('button', { name: '确认发放' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: '工具借还' }))
    await screen.findByText('IT工具借还管理')
    expect(screen.queryByRole('button', { name: /借出工具/ })).toBeNull()
  })
})
