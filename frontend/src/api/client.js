const TOKEN_KEY = 'oneclick_trip_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export async function apiRequest(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }
  const token = getToken()
  if (token) {
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
  return body?.data
}

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
  aiChat(message) {
    return apiRequest('/api/ai/chat', {
      method: 'POST',
      body: JSON.stringify({ message })
    })
  }
}
