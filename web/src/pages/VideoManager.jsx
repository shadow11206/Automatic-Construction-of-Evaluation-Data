import React, { useEffect, useState } from 'react'
import { Card, Table, Button, Upload, Checkbox, Tag, Modal, Space, message, Popconfirm, Radio } from 'antd'
import { InboxOutlined, PlayCircleOutlined, DeleteOutlined, SaveOutlined } from '@ant-design/icons'
import api from '../api'
import { usePipelineStatus } from '../App'

export default function VideoManager() {
  const [videos, setVideos] = useState([])
  const [checked, setChecked] = useState(new Set())
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [playing, setPlaying] = useState(null)
  const [exportFilter, setExportFilter] = useState('all') // all / exported / unexported
  const [selectedForDelete, setSelectedForDelete] = useState([])
  const { status } = usePipelineStatus()
  const running = status?.status === 'running'

  // 按导出状态筛选显示
  const shownVideos = videos.filter(v => {
    if (exportFilter === 'exported') return v.exported_count > 0
    if (exportFilter === 'unexported') return v.exported_count === 0
    return true
  })

  const load = async () => {
    setLoading(true)
    try {
      const res = await api.getVideos()
      setVideos(res.videos)
      setChecked(new Set(res.videos.filter(v => v.in_list).map(v => v.name)))
    } catch { /* 拦截器已提示 */ } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const toggle = (name) => {
    const next = new Set(checked)
    next.has(name) ? next.delete(name) : next.add(name)
    setChecked(next)
  }

  const saveList = async () => {
    setSaving(true)
    try {
      await api.saveVideoList([...checked])
      message.success(`清单已保存（${checked.size} 个视频参与评测）`)
      load()
    } catch { /* 拦截器已提示 */ } finally {
      setSaving(false)
    }
  }

  const batchDelete = async () => {
    try {
      const res = await api.batchDeleteVideos(selectedForDelete)
      const ok = res.deleted.length
      const fail = res.failed.length
      if (fail > 0) message.warning(`${fail} 个删除失败`)
      message.success(`已删除 ${ok} 个视频`)
      setSelectedForDelete([])
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

  const columns = [
    {
      title: '参与', width: 60,
      render: (_, v) => <Checkbox checked={checked.has(v.name)} onChange={() => toggle(v.name)} />,
    },
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
        : (v.in_list ? <Tag color="blue">在清单中</Tag> : <Tag>未参与</Tag>),
    },
    {
      title: '导出状态', width: 130,
      render: (_, v) => v.exported_count > 0
        ? <Tag color="cyan">已导出 {v.exported_count} 条</Tag>
        : <Tag>未导出</Tag>,
    },
    {
      title: '操作', width: 160,
      render: (_, v) => (
        <Space>
          <Button size="small" onClick={() => setPlaying(v.name)}>播放</Button>
          <Popconfirm
            title={v.used_by > 0 ? `该视频已被 ${v.used_by} 条结果引用，删除后这些数据将无法回看视频，确认删除？` : '确认删除该视频？'}
            onConfirm={async () => { await api.deleteVideo(v.name); message.success('已删除'); load() }}
          >
            <Button size="small" danger disabled={running}>删除</Button>
          </Popconfirm>
        </Space>
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
          <Space>
            <Radio.Group size="small" value={exportFilter} onChange={(e) => setExportFilter(e.target.value)}>
              <Radio.Button value="all">全部（{videos.length}）</Radio.Button>
              <Radio.Button value="exported">已导出（{videos.filter(v => v.exported_count > 0).length}）</Radio.Button>
              <Radio.Button value="unexported">未导出（{videos.filter(v => v.exported_count === 0).length}）</Radio.Button>
            </Radio.Group>
            <Button size="small" onClick={() => setChecked(new Set(videos.map(v => v.name)))}>全选</Button>
            <Button size="small" onClick={() => setChecked(new Set())}>清空</Button>
            <Button type="primary" size="small" icon={<SaveOutlined />} loading={saving} onClick={saveList}>
              保存清单（{checked.size}/{videos.length}）
            </Button>
          </Space>
        }
      >
        <Table rowKey="name" loading={loading} columns={columns} dataSource={shownVideos} pagination={false}
          rowSelection={{ selectedRowKeys: selectedForDelete, onChange: setSelectedForDelete }}
        />
        {selectedForDelete.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', justifyContent: 'flex-end' }}>
            <Popconfirm
              title={`确认删除选中的 ${selectedForDelete.length} 个视频？`}
              onConfirm={batchDelete}
            >
              <Button danger icon={<DeleteOutlined />} disabled={running}>
                删除选中（{selectedForDelete.length}）
              </Button>
            </Popconfirm>
          </div>
        )}
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
