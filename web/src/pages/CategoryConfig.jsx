import React, { useEffect, useState } from 'react'
import { Card, Table, Button, Input, InputNumber, AutoComplete, Space, Tag, message, Popconfirm, Alert } from 'antd'
import { PlusOutlined, SaveOutlined, DeleteOutlined } from '@ant-design/icons'
import api from '../api'

export default function CategoryConfig() {
  const [rows, setRows] = useState([])
  const [builtin, setBuiltin] = useState([])
  const [weights, setWeights] = useState({ 简单: 0.3, 中等: 0.4, 困难: 0.3 })
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const [catRes, diffRes] = await Promise.all([api.getCategories(), api.getDifficulty()])
      setRows(catRes.rows.map((r, i) => ({ ...r, _key: i })))
      setBuiltin(catRes.builtin_categories || [])
      if (diffRes.weights) setWeights(diffRes.weights)
    } catch { /* 拦截器已提示 */ } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const total = rows.reduce((s, r) => s + (Number(r.数量) || 0), 0)
  const weightSum = Object.values(weights).reduce((s, v) => s + (Number(v) || 0), 0)
  const weightOk = Math.abs(weightSum - 1.0) <= 0.01

  const updateRow = (key, field, value) => {
    setRows(rows.map(r => (r._key === key ? { ...r, [field]: value } : r)))
  }

  const addRow = () => {
    const key = rows.length ? Math.max(...rows.map(r => r._key)) + 1 : 0
    setRows([...rows, { _key: key, 一级类目: '', 二级类目: '', 数量: 10 }])
  }

  const save = async () => {
    setSaving(true)
    try {
      await api.saveCategories(rows.map(({ 一级类目, 二级类目, 数量 }) => ({ 一级类目, 二级类目, 数量 })))
      if (weightOk) await api.saveDifficulty(weights)
      message.success(`配置已保存，共 ${total} 条任务`)
      load()
    } catch { /* 拦截器已提示 */ } finally {
      setSaving(false)
    }
  }

  const columns = [
    { title: '#', width: 50, render: (_, __, i) => i + 1 },
    {
      title: '一级类目', dataIndex: '一级类目',
      render: (v, r) => (
        <Space size={4}>
          <AutoComplete
            value={v}
            style={{ width: 160 }}
            options={builtin.map(b => ({ value: b }))}
            placeholder="如：动作识别"
            onChange={(val) => updateRow(r._key, '一级类目', val)}
            filterOption={(input, opt) => opt.value.includes(input)}
          />
          {builtin.includes(v)
            ? <Tag color="blue">✦ 内置</Tag>
            : v ? <Tag>未内置</Tag> : null}
        </Space>
      ),
    },
    {
      title: '二级类目', dataIndex: '二级类目',
      render: (v, r) => (
        <Input value={v} placeholder="如：人物动作" style={{ width: 180 }}
          onChange={(e) => updateRow(r._key, '二级类目', e.target.value)} />
      ),
    },
    {
      title: '数量', dataIndex: '数量', width: 120,
      render: (v, r) => (
        <InputNumber value={v} min={1} max={9999} onChange={(val) => updateRow(r._key, '数量', val)} />
      ),
    },
    {
      title: '操作', width: 100,
      render: (_, r) => (
        <Popconfirm title="确认删除该行？" onConfirm={() => setRows(rows.filter(x => x._key !== r._key))}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <Card
        title="类目配置"
        extra={<Tag color="blue">合计 {total} 条任务</Tag>}
      >
        <Table
          rowKey="_key"
          loading={loading}
          columns={columns}
          dataSource={rows}
          pagination={false}
          size="middle"
        />
        <Space style={{ marginTop: 14 }}>
          <Button icon={<PlusOutlined />} onClick={addRow}>添加一行</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} disabled={!weightOk} onClick={save}>
            保存配置
          </Button>
        </Space>
        <Alert
          style={{ marginTop: 14 }}
          type="info"
          showIcon
          message="带「✦ 内置」标记的一级类目在 prompt_templates.py 中有内置引导语，生成质量更稳；未内置类目使用默认引导语并跳过关键词校验。"
        />
      </Card>

      <Card title="难度权重" style={{ marginTop: 16 }}>
        <Space size="large" align="center">
          {['简单', '中等', '困难'].map(d => (
            <span key={d}>
              {d}
              <InputNumber
                style={{ marginLeft: 8, width: 90 }}
                value={Math.round((weights[d] || 0) * 100)}
                min={0} max={100}
                formatter={(v) => `${v}%`}
                parser={(v) => Number(String(v).replace('%', '')) || 0}
                onChange={(val) => setWeights({ ...weights, [d]: (val || 0) / 100 })}
              />
            </span>
          ))}
          {weightOk
            ? <Tag color="green">✓ 合计 100%</Tag>
            : <Tag color="red">合计 {Math.round(weightSum * 100)}%，须等于 100%</Tag>}
        </Space>
      </Card>
    </div>
  )
}
