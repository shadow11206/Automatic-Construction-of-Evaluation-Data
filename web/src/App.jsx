import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Tag, Space, Button } from 'antd'
import {
  DashboardOutlined, AppstoreOutlined, VideoCameraOutlined,
  CheckSquareOutlined, SettingOutlined, StopOutlined,
} from '@ant-design/icons'
import api from './api'
import Dashboard from './pages/Dashboard'
import CategoryConfig from './pages/CategoryConfig'
import VideoManager from './pages/VideoManager'
import ResultReview from './pages/ResultReview'
import Settings from './pages/Settings'

const { Sider, Header, Content } = Layout

// 全局流水线状态：running 时 1s 轮询，平时 5s
const StatusContext = createContext({ status: null, refresh: () => {} })
export const usePipelineStatus = () => useContext(StatusContext)

function useStatusPoller() {
  const [status, setStatus] = useState(null)
  const refresh = useCallback(async () => {
    try {
      const s = await api.getStatus()
      setStatus(s)
      return s
    } catch {
      return null
    }
  }, [])

  useEffect(() => {
    let timer
    const tick = async () => {
      const s = await refresh()
      timer = setTimeout(tick, s?.status === 'running' ? 1000 : 5000)
    }
    tick()
    return () => clearTimeout(timer)
  }, [refresh])

  return { status, refresh }
}

// 顶部流水线状态条节点
function PipeNode({ label, state }) {
  const colorMap = { done: 'success', running: 'processing', idle: 'default', error: 'error', stopped: 'warning' }
  return <Tag color={colorMap[state] || 'default'} style={{ marginInlineEnd: 0 }}>{label}</Tag>
}

function PipelineBar() {
  const { status, refresh } = usePipelineStatus()
  const p = status?.pipeline || {}
  const running = status?.status === 'running'

  const prepareState = p.tasks_count > 0 ? 'done' : 'idle'
  const generateState = running ? 'running'
    : p.results_count > 0 && p.results_count >= p.tasks_count && p.tasks_count > 0 ? 'done'
    : p.results_count > 0 ? 'running' : 'idle'
  const validateState = p.final_exists ? 'done' : 'idle'

  const handleStop = async () => {
    await api.stopGenerate()
    setTimeout(refresh, 500)
  }

  return (
    <Space size="small">
      <PipeNode label={`① 准备 ${p.tasks_count || 0} 条`} state={prepareState} />
      <span style={{ color: '#d9d9d9' }}>→</span>
      <PipeNode
        label={running ? `② 生成中 ${status.done}/${status.total}` : `② 生成 ${p.results_normal || 0}/${p.results_count || 0}`}
        state={generateState}
      />
      <span style={{ color: '#d9d9d9' }}>→</span>
      <PipeNode label="③ 校验" state={validateState} />
      {running && (
        <Button size="small" danger icon={<StopOutlined />} onClick={handleStop}>停止</Button>
      )}
    </Space>
  )
}

const MENU_ITEMS = [
  { key: '/', icon: <DashboardOutlined />, label: '工作台' },
  { key: '/category', icon: <AppstoreOutlined />, label: '类目配置' },
  { key: '/videos', icon: <VideoCameraOutlined />, label: '视频管理' },
  { key: '/results', icon: <CheckSquareOutlined />, label: '结果审核' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const poller = useStatusPoller()

  return (
    <StatusContext.Provider value={poller}>
      <Layout style={{ minHeight: '100vh' }}>
        <Sider theme="dark" width={220}>
          <div style={{
            height: 60, display: 'flex', alignItems: 'center', gap: 10,
            padding: '0 20px', color: '#fff', fontSize: 16, fontWeight: 600,
            borderBottom: '1px solid rgba(255,255,255,.08)',
          }}>
            <span style={{
              width: 30, height: 30, borderRadius: 8, background: '#1677ff',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 15,
            }}>🎬</span>
            VQA 数据工作台
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[location.pathname]}
            items={MENU_ITEMS}
            onClick={({ key }) => navigate(key)}
          />
        </Sider>
        <Layout>
          <Header style={{
            background: '#fff', borderBottom: '1px solid #f0f0f0',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '0 24px', position: 'sticky', top: 0, zIndex: 10,
          }}>
            <span style={{ fontSize: 16, fontWeight: 600 }}>
              {MENU_ITEMS.find(i => i.key === location.pathname)?.label || '工作台'}
            </span>
            <PipelineBar />
          </Header>
          <Content style={{ padding: '20px 24px 40px', background: '#f5f6fa' }}>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/category" element={<CategoryConfig />} />
              <Route path="/videos" element={<VideoManager />} />
              <Route path="/results" element={<ResultReview />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </Content>
        </Layout>
      </Layout>
    </StatusContext.Provider>
  )
}
