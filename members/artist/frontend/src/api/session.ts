import api from './client'
import type { SessionInfo, Message, GenerateRequest, LineageTree } from '../types'

export const sessionApi = {
  list: () => api.get<SessionInfo[]>('/sessions'),

  get: (id: string) => api.get<SessionInfo>(`/sessions/${id}`),

  create: (title: string = '新会话') => api.post<SessionInfo>('/sessions', { title }),

  update: (id: string, data: { title?: string }) => api.put<SessionInfo>(`/sessions/${id}`, data),

  delete: (id: string) => api.delete(`/sessions/${id}`),

  getMessages: (id: string) => api.get<Message[]>(`/sessions/${id}/messages`),

  addMessage: (id: string, data: { content: string; message_type?: string; metadata?: Record<string, unknown> }) =>
    api.post<Message>(`/sessions/${id}/messages`, data),

  generate: (data: GenerateRequest) => api.post(`/sessions/${data.session_id}/artist-turn`, data),

  cancel: (id: string) => api.post(`/sessions/${id}/cancel`),

  getLineageTree: (id: string) => api.get<LineageTree>(`/sessions/${id}/lineage-tree`),

  updateLineageHead: (id: string, imageUrl: string, branchName?: string) =>
    api.put<LineageTree>(`/sessions/${id}/lineage/head`, { image_url: imageUrl, branch_name: branchName }),

  renameLineageBranch: (id: string, branchName: string, newName: string) =>
    api.put<LineageTree>(`/sessions/${id}/lineage/branch-rename`, { branch_name: branchName, new_name: newName }),

  getLongTasks: (id: string) => api.get(`/sessions/${id}/long-tasks`),

  getLongTask: (id: string, taskRunId: string) => api.get(`/sessions/${id}/long-task/${taskRunId}`),

  pauseLongTask: (id: string, taskRunId: string) => api.post(`/sessions/${id}/long-task/${taskRunId}/pause`),

  resumeLongTask: (id: string, taskRunId: string) => api.post(`/sessions/${id}/long-task/${taskRunId}/resume`),

  cancelLongTask: (id: string, taskRunId: string) => api.post(`/sessions/${id}/long-task/${taskRunId}/cancel`),

  checkpointLongTask: (id: string, taskRunId: string, action: string) =>
    api.post(`/sessions/${id}/long-task/${taskRunId}/checkpoint`, { action }),
}
