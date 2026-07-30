import axios from 'axios'
import { message } from 'antd'

// 统一 axios 实例：错误统一 message 提示并 reject
const http = axios.create({ baseURL: '/', timeout: 60000 })

http.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    const detail = err.response?.data?.detail || err.message || '请求失败'
    message.error(typeof detail === 'string' ? detail : JSON.stringify(detail))
    return Promise.reject(err)
  },
)

const api = {
  // 配置
  getCategories: () => http.get('/api/config/categories'),
  saveCategories: (rows) => http.put('/api/config/categories', { rows }),
  getDifficulty: () => http.get('/api/config/difficulty'),
  saveDifficulty: (weights) => http.put('/api/config/difficulty', { weights }),

  // 视频
  getVideos: () => http.get('/api/videos'),
  uploadVideo: (file) => {
    const form = new FormData()
    form.append('file', file)
    return http.post('/api/videos/upload', form, { timeout: 600000 })
  },
  deleteVideo: (name) => http.delete(`/api/videos/${encodeURIComponent(name)}`),
  saveVideoList: (names) => http.put('/api/videos/list', { names }),

  // 流水线
  runPrepare: () => http.post('/api/pipeline/prepare'),
  runGenerate: () => http.post('/api/pipeline/generate'),
  runValidate: () => http.post('/api/pipeline/validate'),
  getStatus: () => http.get('/api/pipeline/status'),
  stopGenerate: () => http.post('/api/pipeline/stop'),

  // 结果
  getResults: (params) => http.get('/api/results', { params }),
  updateResult: (dataId, updates, source = 'results') =>
    http.put(`/api/results/${encodeURIComponent(dataId)}`, { updates }, { params: { source } }),
  rerunResults: (dataIds, source = 'results') =>
    http.post('/api/results/rerun', { data_ids: dataIds, source }),
  // 导出 xlsx：blob 下载，返回 {count, newCount, filename}
  exportResults: async (params) => {
    const resp = await axios.get('/api/results/export', {
      params,
      responseType: 'blob',
      timeout: 120000,
    }).catch((err) => {
      // blob 错误响应需转 JSON 读取 detail
      if (err.response?.data instanceof Blob) {
        err.response.data.text().then((t) => {
          try { message.error(JSON.parse(t).detail || '导出失败') } catch { message.error('导出失败') }
        })
      }
      throw err
    })
    const dispo = resp.headers['content-disposition'] || ''
    const match = dispo.match(/filename\*=UTF-8''([^;]+)/)
    const filename = match ? decodeURIComponent(match[1]) : 'VQA_export.xlsx'
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    return {
      count: Number(resp.headers['x-export-count'] || 0),
      newCount: Number(resp.headers['x-export-new'] || 0),
      filename,
    }
  },

  // 设置
  getSettings: () => http.get('/api/settings'),
  saveSettings: (settings) => http.put('/api/settings', { settings }),
  testSettings: () => http.post('/api/settings/test'),
}

export default api
