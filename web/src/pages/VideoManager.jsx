import React, { useEffect, useState } from 'react'
import { Card, Table, Button, Upload, Tag, Modal, Space, message, Popconfirm, Radio } from 'antd'
import { InboxOutlined, PlayCircleOutlined, DeleteOutlined, SaveOutlined, ClearOutlined } from '@ant-design/icons'
import api from '../api'
import { usePipelineStatus } from '../App'

// 视频库交互约定：
// - 一套勾选（rowSelection）= 视频配置（参与评测的视频），初始为当前已配置清单
// - 头部工具区：状态筛选 / 删除选中 / 清空视频配置 / 保存视频配置
export default function VideoManager() {
  const [videos, setVideos] = useState([])
  const [selected, setSelected] = useState([])   // 勾选 = 视频配置
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [playing, setPlaying] = useState(null)
  const [filter, setFilter] = useState('all')    // all / used / unused / exported / unexported
  const { status } = usePipelineStatus()
  const running = status?.status === 'running'

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.getVideos()
      setVideos(res.videos)
      // 勾选状态 = 当前已保存的视频配置
      setSelected(res.videos.filter(v => v.in_list).map(v => v.name))
    } catch { /* 拦截器已提示 */ } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const saveConfig = async () => {
    setSaving(true)
    try {
      await api.saveVideoList(selected)
      message.success(`视频配置已保存（${selected.length} 个视频参与评测）`)
      load()
    } catch { /* 拦截器已提示 */ } finally {
      setSaving(false)
    }
  }

  const clearConfig = async () => {
    try {
      await api.saveVideoList([])
      setSelected([])
      message.success('视频配置已清空，可重新勾选配置')
      load()
    } catch { /* 拦截器已提示 */ }
  }

  const batchDelete = async () => {
    try {
      const res = await api.batchDeleteVideos(selected)
      if (res.failed.length > 0) {
        message.warning(`已删除 ${res.deleted.length} 个，${res.failed.length} 个删除失败`)
      } else {
        message.success(`已删除 ${res.deleted.length} 个视频`)
      }
      setSelected([])
      load()
    } catch { /* 拦截器已提示 */ }
  }

  const uploadProps = {
    name: 'file',
    multiple: true,
    showUploadList: true,
    accept: '.mp4,.avi,.mov,.mkv,.webm,.flv,.wmv',
    customRequest: async ({ file, onSuccess, onError }) => {
      try {
        await api.uploadVideo(file)
        message.success(`${file.name} 上传完成`)
        onSuccess()
        load()
      } catch (e) {
        onError(e)
      }
    },
  }

  const shownVideos = videos.filter(v => {
    if (filter === 'used') return v.used_by > 0
    if (filter === 'unused') return v.used_by === 0
    if (filter === 'exported') return v.exported_count > 0
    if (filter === 'unexported') return v.exported_count === 0
    return true
  })

  const countOf = (f) => videos.filter(v => {
    if (f === 'used') return v.used_by > 0
    if (f === 'unused') return v.used_by === 0
    if (f === 'exported') return v.exported_count > 0
    if (f === 'unexported') return v.exported_count === 0
    return true
  }).length

  const columns = [
    {
      title: '预览', width: 110,
      render: (_, v) => (
        <div
          onClick={() => setPlaying(v.name)}
          style={{
            width: 96, height: 54, borderRadius: 6, background: '#000', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255,255,255,.85)',
          }}
        >
          <PlayCircleOutlined style={{ fontSize: 20 }} />
        </div>
      ),
    },
    { title: '文件名', dataIndex: 'name' },
    { title: '时长', dataIndex: 'duration', width: 100 },
    { title: '大小', dataIndex: 'size_mb', width: 90, render: (v) => `${v} MB` },
    {
      title: '状态', width: 140,
      render: (_, v) => v.used_by > 0
        ? <Tag color="green">已使用 · {v.used_by} 条</Tag>
        : (v.in_list ? <Tag color="blue">已配置</Tag> : <Tag>未使用</Tag>),
    },
    {
      title: '导出状态', width: 130,
      render: (_, v) => v.exported_count > 0
        ? <Tag color="cyan">已导出 {v.exported_count} 条</Tag>
        : <Tag>未导出</Tag>,
    },
    {
      title: '操作', width: 90,
      render: (_, v) => (
        <Button size="small" onClick={() => setPlaying(v.name)}>播放</Button>
      ),
    },
  ]

  return (
    <div>
      <Card>
        <Upload.Dragger {...uploadProps} disabled={running}>
          <p className="ant-upload-drag-icon"><InboxOutlined /></p>
          <p className="ant-upload-text">点击或拖拽视频到此处上传</p>
          <p className="ant-upload-hint">支持 mp4 / avi / mov / mkv / webm，多文件上传</p>
        </Upload.Dragger>
      </Card>

      <Card
        style={{ marginTop: 16 }}
        title="视频库"
        extra={
          <Space wrap>
            <Radio.Group size="small" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <Radio.Button value="all">全部（{videos.length}）</Radio.Button>
              <Radio.Button value="used">已使用（{countOf('used')}）</Radio.Button>
              <Radio.Button value="unused">未使用（{countOf('unused')}）</Radio.Button>
              <Radio.Button value="exported">已导出（{countOf('exported')}）</Radio.Button>
              <Radio.Button value="unexported">未导出（{countOf('unexported')}）</Radio.Button>
            </Radio.Group>
            <Popconfirm
              title={`确认删除勾选的 ${selected.length} 个视频？（将同时从视频配置中移除）`}
              onConfirm={batchDelete}
              disabled={!selected.length}
            >
              <Button size="small" danger icon={<DeleteOutlined />} disabled={!selected.length || running}>
                删除选中（{selected.length}）
              </Button>
            </Popconfirm>
            <Popconfirm
              title="清空当前视频配置？（用于纠正配置错误，不会删除视频文件）"
              onConfirm={clearConfig}
            >
              <Button size="small" icon={<ClearOutlined />}>清空视频配置</Button>
            </Popconfirm>
            <Button type="primary" size="small" icon={<SaveOutlined />} loading={saving} onClick={saveConfig}>
              保存视频配置（{selected.length}/{videos.length}）
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="name"
          loading={loading}
          columns={columns}
          dataSource={shownVideos}
          pagination={false}
          rowSelection={{
            selectedRowKeys: selected,
            onChange: setSelected,
          }}
        />
        <div style={{ marginTop: 10, fontSize: 12, color: '#999' }}>
          勾选即视频配置：勾选后点「保存视频配置」生效；配置错误的可先「清空视频配置」再重新勾选。
        </div>
      </Card>

      <Modal
        open={!!playing}
        title={playing}
        footer={null}
        onCancel={() => setPlaying(null)}
        width={720}
        destroyOnClose
      >
        {playing && (
          <video
            key={playing}
            src={`/videos/${encodeURIComponent(playing)}`}
            controls
            autoPlay
            style={{ width: '100%', borderRadius: 8, background: '#000' }}
          />
        )}
      </Modal>
    </div>
  )
}
