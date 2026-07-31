import { useState, useEffect } from 'react'
import axios from 'axios'
import { Search, Filter, BarChart2, List } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const API_URL = import.meta.env.VITE_API_URL || ''

function ReturnHistory() {
  const [records, setRecords] = useState([])
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)
  const [viewMode, setViewMode] = useState('list') // 'list' | 'stats'
  const [departments, setDepartments] = useState([])
  const navigate =useNavigate();

  const [filters, setFilters] = useState({
    employee_name: '',
    department: '',
    return_reason: '',
    date_from: '',
    date_to: '',
  })

  useEffect(() => {
    axios.get(`${API_URL}/departments/flat`).then(res => setDepartments(res.data)).catch(() => {})
    fetchSummary()
  }, [])

  useEffect(() => {
    fetchRecords()
  }, [filters])

  const fetchRecords = async () => {
    try {
      setLoading(true)
      const params = { is_returned: true, limit: 500 }
      if (filters.employee_name) params.employee_name = filters.employee_name
      if (filters.department) params.department = filters.department
      if (filters.return_reason) params.return_reason = filters.return_reason
      if (filters.date_from) params.date_from = filters.date_from
      if (filters.date_to) params.date_to = filters.date_to
      const res = await axios.get(`${API_URL}/return-records/`, { params })
      setRecords(res.data)
    } catch (err) {
      console.error('获取历史记录失败:', err)
    } finally {
      setLoading(false)
    }
  }

  const fetchSummary = async () => {
    try {
      const res = await axios.get(`${API_URL}/return-records/history/summary`)
      setSummary(res.data)
    } catch (err) {
      console.error('获取统计数据失败:', err)
    }
  }

  const handleFilterChange = (e) => {
    setFilters({ ...filters, [e.target.name]: e.target.value })
  }

  const handleReset = () => {
    setFilters({ employee_name: '', department: '', return_reason: '', date_from: '', date_to: '' })
  }

  const formatDate = (d) => d ? new Date(d).toLocaleDateString('zh-CN') : '-'
  const formatDateTime = (d) => d ? new Date(d).toLocaleString('zh-CN') : '-'

  const reasonColors = {
    '离职': '#E05252',
    '调岗': '#D4952B',
    '设备更换': '#375B81',
    '其他': '#8E9EA4',
  }

  return (
    <div className="return-history">
      {/* 页头 */}
      <div className="return-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px'}}>
          <button
           className='btn btn-secondary'
           onClick={() => navigate(-1)} //返回上一页
           >
            返回
           </button>
        </div>
        <h2>归还历史记录</h2>

        <div className="header-actions">
          <button
            className={`btn ${viewMode === 'list' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('list')}
          >
            <List size={15} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            列表视图
          </button>
          <button
            className={`btn ${viewMode === 'stats' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setViewMode('stats')}
          >
            <BarChart2 size={15} style={{ verticalAlign: 'middle', marginRight: 4 }} />
            统计视图
          </button>
        </div>
      </div>

      {/* 筛选栏 */}
      <div className="history-filters">
        <div className="filter-row">
          <div className="filter-item">
            <Search size={14} className="filter-icon" />
            <input
              type="text"
              name="employee_name"
              value={filters.employee_name}
              onChange={handleFilterChange}
              placeholder="搜索员工姓名"
              className="filter-input"
            />
          </div>
          <div className="filter-item">
            <select name="department" value={filters.department} onChange={handleFilterChange} className="filter-select">
              <option value="">所有部门</option>
              {departments.map(d => <option key={d.id} value={d.display}>{d.display}</option>)}
            </select>
          </div>
          <div className="filter-item">
            <select name="return_reason" value={filters.return_reason} onChange={handleFilterChange} className="filter-select">
              <option value="">所有原因</option>
              <option value="离职">离职</option>
              <option value="调岗">调岗</option>
              <option value="设备更换">设备更换</option>
              <option value="其他">其他</option>
            </select>
          </div>
          <div className="filter-item">
            <input type="date" name="date_from" value={filters.date_from} onChange={handleFilterChange} className="filter-input" title="开始日期" />
          </div>
          <div className="filter-item">
            <input type="date" name="date_to" value={filters.date_to} onChange={handleFilterChange} className="filter-input" title="结束日期" />
          </div>
          <button className="btn btn-secondary btn-sm" onClick={handleReset}>
            <Filter size={13} style={{ verticalAlign: 'middle', marginRight: 3 }} />
            重置
          </button>
        </div>
        <div className="filter-result-count">
          共 <strong>{records.length}</strong> 条已归还记录
        </div>
      </div>

      {/* 列表视图 */}
      {viewMode === 'list' && (
        <div className="history-table-wrapper">
          {loading ? (
            <div className="loading">加载中...</div>
          ) : records.length === 0 ? (
            <div className="empty-state"><h3>暂无已归还记录</h3></div>
          ) : (
            <table className="history-table">
              <thead>
                <tr>
                  <th>资产名</th>
                  <th>员工姓名</th>
                  <th>工号</th>
                  <th>部门</th>
                  <th>归还原因</th>
                  <th>归还时间</th>
                  <th>登记时间</th>
                  <th>备注</th>
                </tr>
              </thead>
              <tbody>
                {records.map(r => (
                  <tr key={r.id}>
                    <td><span className="asset-name-cell">{r.asset_name}</span></td>
                    <td>{r.employee_name}</td>
                    <td><span className="id-cell">{r.employee_id}</span></td>
                    <td>{r.department || '-'}</td>
                    <td>
                      <span
                        className="reason-badge"
                        style={{ background: reasonColors[r.return_reason] || '#8E9EA4' }}
                      >
                        {r.return_reason}
                      </span>
                    </td>
                    <td>{formatDate(r.return_date)}</td>
                    <td>{formatDateTime(r.created_at)}</td>
                    <td className="notes-cell">{r.notes || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* 统计视图 */}
      {viewMode === 'stats' && summary && (
        <div className="history-stats">
          {/* 按原因分布 */}
          <div className="stats-section">
            <h3>按归还原因分布</h3>
            <div className="stats-bars">
              {summary.by_reason.map(item => {
                const total = summary.by_reason.reduce((s, i) => s + i.count, 0)
                const pct = total > 0 ? Math.round((item.count / total) * 100) : 0
                return (
                  <div key={item.reason} className="stats-bar-row">
                    <div className="stats-bar-label">{item.reason}</div>
                    <div className="stats-bar-track">
                      <div
                        className="stats-bar-fill"
                        style={{ width: `${pct}%`, background: reasonColors[item.reason] || '#8E9EA4' }}
                      />
                    </div>
                    <div className="stats-bar-value">{item.count} 条 ({pct}%)</div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* 按部门分布（Top 10） */}
          <div className="stats-section">
            <h3>按部门分布（已归还 Top 10）</h3>
            <div className="stats-bars">
              {summary.by_department.map((item, idx) => {
                const max = summary.by_department[0]?.count || 1
                const pct = Math.round((item.count / max) * 100)
                return (
                  <div key={idx} className="stats-bar-row">
                    <div className="stats-bar-label">{item.department}</div>
                    <div className="stats-bar-track">
                      <div className="stats-bar-fill" style={{ width: `${pct}%`, background: '#375B81' }} />
                    </div>
                    <div className="stats-bar-value">{item.count} 条</div>
                  </div>
                )
              })}
              {summary.by_department.length === 0 && (
                <div style={{ color: '#8E9EA4', padding: '12px 0' }}>暂无数据</div>
              )}
            </div>
          </div>

          {/* 近30天趋势 */}
          <div className="stats-section">
            <h3>近30天归还趋势</h3>
            {summary.daily_trend.length === 0 ? (
              <div style={{ color: '#8E9EA4', padding: '12px 0' }}>近30天暂无归还记录</div>
            ) : (
              <div className="trend-chart">
                {summary.daily_trend.map(item => {
                  const max = Math.max(...summary.daily_trend.map(d => d.count), 1)
                  const heightPct = Math.round((item.count / max) * 100)
                  return (
                    <div key={item.date} className="trend-bar-col" title={`${item.date}: ${item.count} 条`}>
                      <div className="trend-bar-value">{item.count}</div>
                      <div className="trend-bar-wrap">
                        <div className="trend-bar-fill" style={{ height: `${heightPct}%` }} />
                      </div>
                      <div className="trend-bar-date">{item.date.slice(5)}</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default ReturnHistory
