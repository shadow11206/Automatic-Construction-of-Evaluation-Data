import React, { useEffect, useState } from 'react'
import { Card, Steps, Button, Progress, Row, Col, Statistic, Space, message } from 'antd'
import {
  PlayCircleOutlined, ReloadOutlined, CheckCircleOutlined,
  SyncOutlined, StopOutlined,
} from '@ant-design/icons'
import api from '../api'
import { usePipelineStatus } from '../App'

const DIFF_COLORS = { 简单: '#52c41a', 中等: '#1677ff', 困难: '#faad14' }

function Distribution({ title, data, colorMap }) {
  const entries = Object.entries(data || {})
  const max = Math.max(...entries.map(([, v]) => v), 1)
  if (!entries.length) return <div style={{ color: '#999', fontSize: 13 }}>暂无数据</div>
  return (
    <div>
      <div style={{ fontWeight: 600, marginBottom: 10, fontSize: 13 }}>{title}</div>
      {entries.map(([k, v], i) => (
        <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, fontSize: 13 }}>
          <span style={{ width: 130, flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{k}</span>
          <div style={{ flex: 1, height: 12, background: '#f5f5f5', borderRadius: 6, overflow: 'hidden' }}>
            <div style={{
              height: '100%', borderRadius: 6, width: `${(v / max) * 100}%`,
              background: colorMap?.[k] || ['#1677ff', '#2fc25b', '#faad14', '#722ed1', '#eb2f96'][i % 5],
            }} />
          </div>
          <span style={{ width: 50, textAlign: 'right', color: '#999', flexShrink: 0 }}>{v} 条</span>
        </div>
      ))}
    </div>
  )
}

export default function Dashboard() {
  const { status, refresh } = usePipelineStatus()
  const [busy, setBusy] = useState('')
  const [preview, setPreview] = useState(null)
  const running = status?.status === 'running'
  const p = status?.pipeline || {}

  const step1 = p.tasks_count > 0 ? 'finish' : 'wait'
  const step2 = running ? 'process' : (p.results_count > 0 ? 'finish' : 'wait')
  const step3 = p.final_exists ? 'finish' : 'wait'
  const current = running ? 1 : (p.final_exists ? 3 : (p.results_count > 0 ? 2 : (p.tasks_count > 0 ? 1 : 0)))

  const loadPreview = async () => {
    if (!p.tasks_count || running) return
    try {
      const res = await api.getPreview()
      setPreview(res)
    } catch { /* 静默 */ }
  }
  useEffect(() => { loadPreview() }, [p.tasks_count, p.results_count, running])

  const doAction = async (name, fn, okMsg) => {
    setBusy(name)
    try {
      const res = await fn()
      message.success(typeof okMsg === 'function' ? okMsg(res) : okMsg)
      refresh()
    } catch { /* 拦截器已提示 */ } finally {
      setBusy('')
    }
  }

  const percent = status?.total ? Math.round((status.done / status.total) * 100) : 0

  // 生成按钮状态：有新任务时用「生成新任务」，上次生成中断时用「继续生成」（由后端记录判定）
  const pendingCount = preview?.pending
  const hasPending = pendingCount !== undefined && pendingCount > 0
  const interrupted = preview?.interrupted === true && hasPending   // 中断且还有未完成任务
  const canNewGenerate = hasPending && !interrupted

  return (
    <div>
      <Card title="流水线" extra={<span style={{ color: '#999', fontSize: 12 }}>三步生成 VQA 评测数据集 · 断点续跑已启用</span>}>
        <Steps
          current={current}
          items={[
            { title: '① 准备任务', description: p.tasks_count ? `${p.tasks_count} 条任务` : '未开始', status: step1 },
            { title: '② 生成数据', description: running ? `进行中 ${status.done}/${status.total}` : (p.results_count ? `已生成 ${p.results_count} 条` : '未开始'), status: step2 },
            { title: '③ 校验结果', description: p.final_exists ? '已完成' : '等待上一步', status: step3 },
          ]}
        />
        <Space style={{ marginTop: 20, justifyContent: 'center', display: 'flex' }} wrap>
          <Button icon={<ReloadOutlined />} loading={busy === 'prepare'} disabled={running}
            onClick={() => doAction('prepare', api.runPrepare, (r) => `已生成 ${r.total} 条任务`)}>
            {p.tasks_count ? '重新准备' : '开始准备'}
          </Button>
          <Button type="primary" icon={<PlayCircleOutlined />} loading={busy === 'generate'}
            disabled={running || !p.tasks_count || !canNewGenerate}
            title={!hasPending ? '所有任务已完成' : '上次生成未完成，请使用「继续生成」'}
            onClick={() => doAction('generate', api.runGenerate, '生成任务已启动')}>
            {preview && canNewGenerate ? `生成新任务（${pendingCount} 条）` : '生成新任务'}
          </Button>
          <Button icon={<ReloadOutlined />} loading={busy === 'generate'} disabled={running || !p.tasks_count || !interrupted}
            title={!hasPending ? '所有任务已完成' : '有新任务时请使用「生成新任务」'}
            onClick={() => doAction('generate', api.runGenerate, '继续生成已启动')}>
            {interrupted ? `继续生成（${pendingCount} 条未完成）` : '继续生成'}
          </Button>
          {running && (
            <Button danger icon={<StopOutlined />} onClick={async () => { await api.stopGenerate(); setTimeout(refresh, 500) }}>
              停止
            </Button>
          )}
          <Button icon={<CheckCircleOutlined />} loading={busy === 'validate'} disabled={running || !p.results_count}
            onClick={() => doAction('validate', api.runValidate, (r) => `校验完成，通过率 ${r.pass_rate}%`)}>
            开始校验
          </Button>
        </Space>
      </Card>

      <Row gutter={16} style={{ marginTop: 16 }}>
        <Col xs={24} lg={12}>
          <Card title="生成进度" extra={running && <span style={{ fontSize: 12, color: '#1677ff' }}><SyncOutlined spin /> {status.current_item}</span>}>
            {running || status?.total ? (
              <>
                <Progress percent={percent} status={running ? 'active' : (status?.status === 'error' ? 'exception' : 'success')}
                  format={() => `${status.done}/${status.total}`} />
                {status?.skipped > 0 && <div style={{ fontSize: 12, color: '#999', marginBottom: 8 }}>断点续跑：已跳过 {status.skipped} 条已完成</div>}
              </>
            ) : (
              <div style={{ color: '#999', fontSize: 13, marginBottom: 12 }}>尚未开始生成。先执行「准备任务」，再点击「开始生成」。</div>
            )}
            <div style={{
              background: '#0d1117', borderRadius: 8, padding: '12px 14px', height: 220,
              overflowY: 'auto', fontFamily: 'Menlo, monospace', fontSize: 12, lineHeight: 1.9,
            }}>
              {(status?.logs || []).length === 0 && <div style={{ color: '#8b949e' }}>暂无日志</div>}
              {(status?.logs || []).map((l, i) => (
                <div key={i}>
                  <span style={{ color: '#8b949e' }}>{l.time} </span>
                  <span style={{ color: l.level === 'warn' ? '#f0b72f' : l.level === 'error' ? '#ff7b72' : '#7ee787' }}>{l.msg}</span>
                </div>
              ))}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="数据集概况">
            <Row gutter={16} style={{ marginBottom: 20 }}>
              <Col span={6}><Statistic title="总任务" value={p.tasks_count || 0} /></Col>
              <Col span={6}><Statistic title="已生成" value={p.results_count || 0} /></Col>
              <Col span={6}><Statistic title="正常" value={p.results_normal || 0} valueStyle={{ color: '#52c41a' }} /></Col>
              <Col span={6}><Statistic title="需复核" value={(p.results_count || 0) - (p.results_normal || 0)} valueStyle={{ color: '#faad14' }} /></Col>
            </Row>
            <Distribution title="难度分布（任务清单）" data={status?.summary?.difficulty_dist} colorMap={DIFF_COLORS} />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
