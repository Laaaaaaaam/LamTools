import axios from 'axios'

export const API_BASE = import.meta.env.VITE_API_BASE
  || (import.meta.env.DEV ? 'http://127.0.0.1:6171/api' : '/api')

const api = axios.create({
  baseURL: API_BASE,
  timeout: 600000,
  headers: {
    'Content-Type': 'application/json',
  },
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const data = error.response?.data
    const status = error.response?.status
    const statusText = status ? `[${status}] ` : ''
    const detail = data?.detail || data?.error || error.message || 'Request failed'
    const message = status ? `${statusText}${detail}` : detail
    return Promise.reject(new Error(message))
  }
)

export default api
