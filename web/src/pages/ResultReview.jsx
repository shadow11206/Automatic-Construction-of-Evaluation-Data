import React, { useEffect, useMemo, useState } from 'react'
import {
  Card, Table, Button, Select, Input, Tag, Drawer, Space, message,
  Popconfirm, Alert, Radio, Tooltip,
} from 'antd'
import { ReloadOutlined, DeleteOutlined, DownloadOutlined } from '@ant-design/icons'
import api from '../api'
import { usePipelineStatus } from '../App'

const VERDICT_COLORS = { 通过: 'green', 需复核: 'orange', 需重生成: 'red', 正常: 'green' }
const DIFF_COLORS = { 简单: 'green', 中等: 'blue', 困难: 'orange' }

export default function ResultReview() {
  const [source, setSource] = useState('results')
  const [items, setItems] = useState([])
  const [stats, setStats] = useState({})
  const [total, setTotal] = useState(0)
  const [exportedIds, setExportedIds] = useState(new Set())
  const [exporting, setExporting] = useState(false)
  const [loading, setLoading] = useState(false)
  const [filters, setFilters] = useState({ cat: '', difficulty: '', verdict: '', q: '', exported: '' })
  const [selected, setSelected] = useState([])
  const [editing, setEditing] = useState(null)   // Drawer 中正在审核的记录
  const [draft, setDraft] = useState({})          // 编辑草稿
  const { status } = usePipelineStatus()
  const running = status?.status === 'running'

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.getResults({ source, ...filters })
      setItems(res.items)
      setStats(res.stats || {})
      setTotal(res.total || 0)
      setExportedIds(new Set(res.exported_ids || []))
    } catch { /* 拦截器已提示 */ } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [source])
  // 筛选变化防抖查询
  useEffect(() => {
    const t = setTimeout(load, 400)
    return () => clearTimeout(t)
  }, [filters])

  const verdictField = source === 'final' ? '校验结果' : '状态'
  const categories = useMemo(() => [...new Set(items.map(i => i.一级类目).filter(Boolean))], [items])

  const openReview = (record) => {
    setEditing(record)
    setDraft({ prompt: record.prompt, 参考答案: record.参考答案, 难度: record.难度 })
  }

  const saveEdit = async () => {
    try {
      await api.updateResult(editing.data_id, draft, source)
      message.success('已保存修改')
      setEditing(null)
      load()
    } catch { /* 拦截器已提示 */ }
  }

  const batchRerun = async () => {
    try {
      const res = await api.rerunResults(selected, source)
      message.success(`已标记 ${res.removed} 条，下次生成时将自动重跑`)
      setSelected([])
      load()
    } catch { /* 拦截器已提示 */ }
  }

  const doExport = async () => {
    setExporting(true)
    try {
      const res = await api.exportResults({ source, ...filters })
      message.success(`已导出 ${res.count} 条到 ${res.filename}（其中 ${res.newCount} 条为首次导出）`)
      load() // 刷新已导出标记
    } catch { /* 已提示 */ } finally {
      setExporting(false)
    }
  }

  const columns = [
    { title: 'data_id', dataIndex: 'data_id', width: 130,
      render: (v) => (
        <Space size={4}>
          <span>{v}</span>
          {exportedIds.has(v) && <Tag color="cyan" style={{ marginInlineEnd: 0 }}>已导出</Tag>}
        </Space>
      ),
    },
    {
      title: '类目', width: 150,
      render: (_, r) => <span>{r.一级类目}<span style={{ color: '#bbb' }}>/</span>{r.二级类目}</span>,
    },
    { title: '视频', dataIndex: '视频url', width: 120 },
    {
      title: 'prompt', dataIndex: 'prompt',
      render: (v) => v
        ? <Tooltip title={v}><span style={{ display: 'inline-block', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' }}>{v}</span></Tooltip>
        : <span style={{ color: '#bbb' }}>（空）</span>,
    },
    {
      title: '参考答案', dataIndex: '参考答案',
      render: (v) => v
        ? <Tooltip title={v}><span style={{ display: 'inline-block', maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', verticalAlign: 'bottom' }}>{v}</span></Tooltip>
        : <span style={{ color: '#bbb' }}>（空）</span>,
    },
    {
      title: '难度', dataIndex: '难度', width: 80,
      render: (v) => DIFF_COLORS[v] ? <Tag color={DIFF_COLORS[v]}>{v}</Tag> : <Tag>{v || '—'}</Tag>,
    },
    {
      title: verdictField, dataIndex: verdictField, width: 100,
      render: (v) => <Tag color={VERDICT_COLORS[v] || 'default'}>{v || '—'}</Tag>,
    },
    {
      title: '操作', width: 90,
      render: (_, r) => <Button size="small" onClick={() => openReview(r)}>审核</Button>,
    },
  ]

  return (
    <div>
      <Card>
        <Space wrap size="small">
          <Radio.Group value={source} onChange={(e) => { setSource(e.target.value); setSelected([]) }}>
            <Radio.Button value="results">生成结果（results）</Radio.Button>
            <Radio.Button value="final">校验结果（final）</Radio.Button>
          </Radio.Group>
          <Select
            style={{ width: 140 }} placeholder="校验结果：全部" allowClear
            value={filters.verdict || undefined}
            onChange={(v) => setFilters({ ...filters, verdict: v || '' })}
            options={Object.keys(stats).map(s => ({ value: s, label: `${s}（${stats[s]}）` }))}
          />
          <Select
            style={{ width: 140 }} placeholder="类目：全部" allowClear
            value={filters.cat || undefined}
            onChange={(v) => setFilters({ ...filters, cat: v || '' })}
            options={categories.map(c => ({ value: c, label: c }))}
          />
          <Select
            style={{ width: 130 }} placeholder="难度：全部" allowClear
            value={filters.difficulty || undefined}
            onChange={(v) => setFilters({ ...filters, difficulty: v || '' })}
            options={['简单', '中等', '困难'].map(d => ({ value: d, label: d }))}
          />
          <Select
            style={{ width: 130 }}
            value={filters.exported || 'all'}
            onChange={(v) => setFilters({ ...filters, exported: v === 'all' ? '' : v })}
            options={[
              { value: 'all', label: '导出：全部' },
              { value: 'yes', label: '已导出' },
              { value: 'no', label: '未导出' },
            ]}
          />
          <Input.Search
            style={{ width: 220 }} placeholder="搜索 prompt / 答案关键词" allowClear
            onSearch={(v) => setFilters({ ...filters, q: v })}
            onChange={(e) => !e.target.value && setFilters({ ...filters, q: '' })}
          />
          <span style={{ flex: 1 }} />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<DownloadOutlined />} loading={exporting} onClick={doExport}>
            导出 Excel
          </Button>
          <Popconfirm title={`标记 ${selected.length} 条重跑？（将从结果中移除，下次生成自动补跑）`} onConfirm={batchRerun} disabled={!selected.length}>
            <Button icon={<ReloadOutlined />} disabled={!selected.length || running}>标记重跑（{selected.length}）</Button>
          </Popconfirm>
          <Popconfirm title={`删除 ${selected.length} 条记录？`} onConfirm={batchRerun} disabled={!selected.length}>
            <Button danger icon={<DeleteOutlined />} disabled={!selected.length || running}>删除（{selected.length}）</Button>
          </Popconfirm>
        </Space>
        <div style={{ marginTop: 10, fontSize: 12, color: '#999' }}>
          共 {total} 条
          {Object.entries(stats).map(([k, v]) => (
            <Tag key={k} color={VERDICT_COLORS[k] || 'default'} style={{ marginLeft: 6 }}>{k} {v}</Tag>
          ))}
        </div>
      </Card>

      <Card style={{ marginTop: 16 }}>
        <Table
          rowKey="data_id"
          loading={loading}
          columns={columns}
          dataSource={items}
          rowSelection={{ selectedRowKeys: selected, onChange: setSelected }}
          pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
          size="middle"
        />
      </Card>

      <Drawer
        open={!!editing}
        width={860}
        title={editing ? `审核 ${editing.data_id} · ${editing.一级类目}/${editing.二级类目}` : ''}
        onClose={() => setEditing(null)}
        extra={editing && (
          <Space>
            <Tag color={VERDICT_COLORS[editing[verdictField]] || 'default'}>{editing[verdictField] || '—'}</Tag>
            <Button type="primary" onClick={saveEdit}>保存修改</Button>
          </Space>
        )}
      >
        {editing && (
          <div style={{ display: 'flex', gap: 20, height: '100%' }}>
            <div style={{ flex: '0 0 380px' }}>
              <video
                key={editing.视频url}
                src={`/videos/${encodeURIComponent(editing.视频url)}`}
                controls
                style={{ width: '100%', borderRadius: 8, background: '#000' }}
              />
              <div style={{ marginTop: 10, fontSize: 12, color: '#999' }}>
                {editing.视频url} · {editing.视频时长}
              </div>
              {editing.问题详情 && (
                <Alert style={{ marginTop: 12 }} type="warning" showIcon message="校验发现的问题"
                  description={<pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontSize: 12 }}>{editing.问题详情}</pre>} />
              )}
              {editing.备注 && (
                <Alert style={{ marginTop: 12 }} type="info" showIcon message="生成备注" description={editing.备注} />
              )}
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>prompt（问题）</div>
                <Input.TextArea rows={4} value={draft.prompt}
                  onChange={(e) => setDraft({ ...draft, prompt: e.target.value })} />
              </div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>参考答案</div>
                <Input.TextArea rows={5} value={draft.参考答案}
                  onChange={(e) => setDraft({ ...draft, 参考答案: e.target.value })} />
              </div>
              <div>
                <span style={{ fontWeight: 600, marginRight: 10 }}>难度</span>
                <Radio.Group value={draft.难度} onChange={(e) => setDraft({ ...draft, 难度: e.target.value })}>
                  {['简单', '中等', '困难'].map(d => <Radio.Button key={d} value={d}>{d}</Radio.Button>)}
                </Radio.Group>
              </div>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  )
}
