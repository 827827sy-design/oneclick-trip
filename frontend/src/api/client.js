const TOKEN_KEY = 'oneclick_trip_token'
const AI_CONVERSATION_KEY = 'oneclick_trip_ai_conversation_id'
let activeAiConversationId = localStorage.getItem(AI_CONVERSATION_KEY) || ''

export function getAiConversationId() {
  return activeAiConversationId
}

export function setAiConversationId(conversationId) {
  activeAiConversationId = conversationId || ''
  if (activeAiConversationId) {
    localStorage.setItem(AI_CONVERSATION_KEY, activeAiConversationId)
  } else {
    localStorage.removeItem(AI_CONVERSATION_KEY)
  }
}

export function resetAiConversationId() {
  setAiConversationId('')
}

function ensureAiConversationId() {
  if (!activeAiConversationId) {
    setAiConversationId(crypto.randomUUID())
  }
  return activeAiConversationId
}

// token 保存在 localStorage，刷新页面后仍然能保持登录态。
export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
  resetAiConversationId()
}

export async function apiRequest(path, options = {}) {
  // 所有接口统一走这个函数：自动加 JSON 请求头、自动带登录 token、统一处理错误。
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }
  const token = getToken()
  if (token) {
    // 后端 JwtAuthenticationFilter 会读取这个请求头。
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(path, {
    ...options,
    headers
  })
  const body = await response.json().catch(() => null)
  if (!response.ok || body?.success === false) {
    throw new Error(body?.message || `请求失败：${response.status}`)
  }
  // 后端统一返回 { success, message, data }，前端页面通常只需要 data。
  return body?.data
}

// 页面里只调用 api.login、api.cities 这种语义化方法，不直接写 fetch。
export const api = {
  login(payload) {
    return apiRequest('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  },
  register(payload) {
    return apiRequest('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  },
  me() {
    return apiRequest('/api/users/me')
  },
  updateProfile(payload) {
    return apiRequest('/api/users/me', {
      method: 'PUT',
      body: JSON.stringify(payload)
    })
  },
  cities() {
    return apiRequest('/api/cities')
  },
  city(id) {
    return apiRequest(`/api/cities/${id}`)
  },
  spots(cityId) {
    return apiRequest(`/api/cities/${cityId}/spots`)
  },
  foods(cityId) {
    return apiRequest(`/api/cities/${cityId}/foods`)
  },
  hotels(cityId) {
    return apiRequest(`/api/cities/${cityId}/hotels`)
  },
  templates(cityId) {
    const query = cityId ? `?cityId=${cityId}` : ''
    return apiRequest(`/api/trip-templates${query}`)
  },
  generatePlan(payload) {
    return apiRequest('/api/trip-plans/generate', {
      method: 'POST',
      body: JSON.stringify(payload)
    })
  },
  aiConversations() {
    return apiRequest('/api/ai/conversations')
  },
  createAiConversation(title = '') {
    return apiRequest('/api/ai/conversations', {
      method: 'POST',
      body: JSON.stringify({ title })
    })
  },
  aiConversation(conversationId) {
    return apiRequest(`/api/ai/conversations/${conversationId}`)
  },
  renameAiConversation(conversationId, title) {
    return apiRequest(`/api/ai/conversations/${conversationId}`, {
      method: 'PUT',
      body: JSON.stringify({ title })
    })
  },
  deleteAiConversation(conversationId) {
    return apiRequest(`/api/ai/conversations/${conversationId}`, { method: 'DELETE' })
  },
  aiChat(message) {
    return apiRequest('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ conversationId: ensureAiConversationId(), message })
    })
  },
  aiResume(confirmed) {
    return apiRequest('/api/ai/resume', {
      method: 'POST',
      body: JSON.stringify({ conversationId: ensureAiConversationId(), confirmed })
    })
  }
}
