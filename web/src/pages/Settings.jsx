import React, { useEffect, useState } from 'react'
import { Card, Form, Select, Input, InputNumber, Switch, Button, Space, Tag, Alert, message } from 'antd'
import { SaveOutlined, ApiOutlined } from '@ant-design/icons'
import api from '../api'

const PROVIDER_META = {
  dashscope:  { label: '阿里云百炼 DashScope（原生视频理解）', modelHint: '如 qwen-vl-max 等', hint: '✅ DashScope 原生支持视频输入，直接复用现有调用链路，效果最稳定', hideUrl: true },
  openai:     { label: 'OpenAI', modelHint: '需支持图片输入的多模态模型，如 gpt-4o', hint: '⚠️ 非 DashScope 平台将自动转为「抽帧 + 图片」方式调用，视频理解效果取决于所选模型' },
  openrouter: { label: 'OpenRouter', modelHint: '如 openai/gpt-4o、google/gemini-2.5-pro', hint: '⚠️ 非 DashScope 平台将自动转为「抽帧 + 图片」方式调用，视频理解效果取决于所选模型' },
  zhipu:      { label: '智谱 GLM', modelHint: '如 glm-4v-plus 等', hint: '⚠️ 非 DashScope 平台将自动转为「抽帧 + 图片」方式调用，视频理解效果取决于所选模型' },
  custom:     { label: '自定义（OpenAI 兼容接口）', modelHint: '你的模型名', hint: '⚠️ 任何兼容 OpenAI Chat Completions 格式的接口均可接入；将采用「抽帧 + 图片」方式调用' },
}

export default function Settings() {
  const [form] = Form.useForm()
  const [settings, setSettings] = useState(null)
  const [provider, setProvider] = useState('dashscope')
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)

  const load = async () => {
    try {
      const s = await api.getSettings()
      setSettings(s)
      setProvider(s.active_provider)
      const prof = s.providers[s.active_provider] || {}
      form.setFieldsValue({
        max_frames: s.max_frames,
        max_retries: s.max_retries,
        keyword_check: s.keyword_check,
        api_key: prof.api_key,
        base_url: prof.base_url,
        model: prof.model,
      })
    } catch { /* 拦截器已提示 */ }
  }
  useEffect(() => { load() }, [])

  // 切换平台：先缓存当前表单到本地 state，再加载目标平台 profile
  const switchProvider = (next) => {
    const cur = form.getFieldsValue(['api_key', 'base_url', 'model'])
    const snapshot = { ...settings }
    snapshot.providers[provider] = { ...snapshot.providers[provider], ...cur }
    setSettings(snapshot)
    setProvider(next)
    const prof = snapshot.providers[next] || {}
    form.setFieldsValue({ api_key: prof.api_key, base_url: prof.base_url, model: prof.model })
  }

  const save = async () => {
    const v = form.getFieldsValue()
    setSaving(true)
    try {
      const payload = {
        active_provider: provider,
        max_frames: v.max_frames,
        max_retries: v.max_retries,
        keyword_check: v.keyword_check,
        providers: { [provider]: { api_key: v.api_key, base_url: v.base_url, model: v.model } },
      }
      const saved = await api.saveSettings(payload)
      setSettings(saved)
      message.success('设置已保存，立即生效')
    } catch { /* 拦截器已提示 */ } finally {
      setSaving(false)
    }
  }

  const test = async () => {
    await save() // 先保存再测试，保证测试的是当前填写内容
    setTesting(true)
    try {
      const res = await api.testSettings()
      res.success ? message.success(res.message) : message.warning(res.message)
    } catch { /* 拦截器已提示 */ } finally {
      setTesting(false)
    }
  }

  const meta = PROVIDER_META[provider]

  return (
    <Card title="模型与生成设置" style={{ maxWidth: 760 }}
      extra={<span style={{ color: '#999', fontSize: 12 }}>保存后立即生效，无需重启 · 各平台配置独立保存</span>}>
      <Form form={form} layout="vertical" style={{ maxWidth: 560 }}>
        <Form.Item label="API 平台" required>
          <Select
            value={provider}
            onChange={switchProvider}
            options={Object.entries(PROVIDER_META).map(([k, m]) => ({ value: k, label: m.label }))}
          />
        </Form.Item>
        {!meta.hideUrl && (
          <Form.Item name="base_url" label="Base URL" extra="已按平台预填，可修改">
            <Input placeholder="https://..." />
          </Form.Item>
        )}
        <Form.Item name="api_key" label="API Key" required extra="仅存本地 server/settings.json，接口不回显完整密钥">
          <Input.Password placeholder="sk-..." autoComplete="off" />
        </Form.Item>
        <Form.Item name="model" label="模型名称" extra={meta.modelHint}>
          <Input />
        </Form.Item>
        <Alert type={provider === 'dashscope' ? 'success' : 'warning'} showIcon message={meta.hint}
          style={{ marginBottom: 20 }} />
        <Form.Item name="max_frames" label="最大抽帧数" extra="帧数越多越准，但越慢越贵（1~512）">
          <InputNumber min={1} max={512} style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="max_retries" label="失败重试次数" extra="单条生成失败后的自动重试次数">
          <InputNumber min={0} max={5} style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="keyword_check" label="关键词校验" valuePropName="checked"
          extra="校验 prompt 与类目关键词是否匹配（未内置类目自动跳过）">
          <Switch />
        </Form.Item>
        <Space>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>保存设置</Button>
          <Button icon={<ApiOutlined />} loading={testing} onClick={test}>测试 API 连通性</Button>
          {settings?.providers?.[provider]?.has_key && <Tag color="green">已配置 Key</Tag>}
        </Space>
      </Form>
    </Card>
  )
}
