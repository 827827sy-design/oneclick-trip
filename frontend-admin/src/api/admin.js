const TOKEN_KEY = 'oneclick_trip_token'
const BASE = '/api/admin'

function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

async function request(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  }
  const token = getToken()
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const response = await fetch(path, { ...options, headers })
  const body = await response.json().catch(() => null)

  if (!response.ok || body?.success === false) {
    throw new Error(body?.message || `请求失败：${response.status}`)
  }
  return body?.data
}

// ===== 仪表盘 =====
export function fetchDashboard() {
  return request(`${BASE}/dashboard`)
}

// ===== 用户管理 =====
export function fetchUsers(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`${BASE}/users?${query}`)
}

export function fetchUser(id) {
  return request(`${BASE}/users/${id}`)
}

export function updateUserStatus(id, status) {
  return request(`${BASE}/users/${id}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status })
  })
}

// ===== AI 会话管理 =====
export function fetchConversations(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`${BASE}/conversations?${query}`)
}

export function fetchConversation(id) {
  return request(`${BASE}/conversations/${id}`)
}

export function deleteConversation(id) {
  return request(`${BASE}/conversations/${id}`, { method: 'DELETE' })
}

// ===== 城市管理 =====
export function fetchCities(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`${BASE}/cities?${query}`)
}

export function fetchCity(id) {
  return request(`${BASE}/cities/${id}`)
}

export function createCity(data) {
  return request(`${BASE}/cities`, {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

export function updateCity(id, data) {
  return request(`${BASE}/cities/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  })
}

export function deleteCity(id) {
  return request(`${BASE}/cities/${id}`, { method: 'DELETE' })
}

// ===== 景点管理 =====
export function fetchSpots(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`${BASE}/spots?${query}`)
}

export function fetchSpot(id) {
  return request(`${BASE}/spots/${id}`)
}

export function createSpot(data) {
  return request(`${BASE}/spots`, {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

export function updateSpot(id, data) {
  return request(`${BASE}/spots/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  })
}

export function deleteSpot(id) {
  return request(`${BASE}/spots/${id}`, { method: 'DELETE' })
}

// ===== 美食管理 =====
export function fetchFoods(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`${BASE}/foods?${query}`)
}

export function fetchFood(id) {
  return request(`${BASE}/foods/${id}`)
}

export function createFood(data) {
  return request(`${BASE}/foods`, {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

export function updateFood(id, data) {
  return request(`${BASE}/foods/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  })
}

export function deleteFood(id) {
  return request(`${BASE}/foods/${id}`, { method: 'DELETE' })
}

// ===== 酒店管理 =====
export function fetchHotels(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`${BASE}/hotels?${query}`)
}

export function fetchHotel(id) {
  return request(`${BASE}/hotels/${id}`)
}

export function createHotel(data) {
  return request(`${BASE}/hotels`, {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

export function updateHotel(id, data) {
  return request(`${BASE}/hotels/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  })
}

export function deleteHotel(id) {
  return request(`${BASE}/hotels/${id}`, { method: 'DELETE' })
}

// ===== 行程模板管理 =====
export function fetchTemplates(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`${BASE}/templates?${query}`)
}

export function fetchTemplate(id) {
  return request(`${BASE}/templates/${id}`)
}

export function createTemplate(data) {
  return request(`${BASE}/templates`, {
    method: 'POST',
    body: JSON.stringify(data)
  })
}

export function updateTemplate(id, data) {
  return request(`${BASE}/templates/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data)
  })
}

export function deleteTemplate(id) {
  return request(`${BASE}/templates/${id}`, { method: 'DELETE' })
}

// ===== 行程订单管理 =====
export function fetchTripPlans(params = {}) {
  const query = new URLSearchParams(params).toString()
  return request(`${BASE}/trip-plans?${query}`)
}

export function fetchTripPlan(id) {
  return request(`${BASE}/trip-plans/${id}`)
}

export function deleteTripPlan(id) {
  return request(`${BASE}/trip-plans/${id}`, { method: 'DELETE' })
}

// ===== 登录 =====
export function adminLogin(payload) {
  return request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}
