<template>
  <div class="admin-layout">
    <!-- 侧边栏 -->
    <aside class="admin-sidebar">
      <div class="sidebar-brand">
        <span class="brand-icon">🧭</span>
        <div class="brand-text">
          <h2>一键游</h2>
          <small>管理系统</small>
        </div>
      </div>

      <nav class="sidebar-nav">
        <div class="nav-section">主导航</div>
        <router-link
          v-for="item in mainNavItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="active"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </router-link>

        <div class="nav-section">内容管理</div>
        <router-link
          v-for="item in contentNavItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="active"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </router-link>

        <div class="nav-section">订单管理</div>
        <router-link
          v-for="item in orderNavItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          active-class="active"
        >
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="user-info">
          <span>👤</span>
          <span>{{ currentUser?.nickname || '管理员' }}</span>
        </div>
        <button class="logout-btn" @click="handleLogout">退出</button>
      </div>
    </aside>

    <!-- 主内容区 -->
    <div class="admin-main">
      <header class="admin-header">
        <div class="page-title">
          <span class="title-icon">{{ currentPageIcon }}</span>
          <span>{{ currentPageTitle }}</span>
        </div>
        <div class="header-actions">
          <el-tag type="success" size="small" effect="plain">在线</el-tag>
          <span style="font-size:13px;color:var(--admin-text-muted)">
            {{ currentUser?.username || 'admin' }}
          </span>
        </div>
      </header>

      <div class="admin-content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Odometer, User, MapLocation, Picture,
  Dish, OfficeBuilding, Collection, List, ChatLineRound, DataAnalysis, DataLine
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const USER_KEY = 'oneclick_trip_user'
const TOKEN_KEY = 'oneclick_trip_token'

const currentUser = computed(() => {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY))
  } catch {
    return null
  }
})

const currentPageTitle = computed(() => route.meta?.title || '仪表盘')
const currentPageIcon = computed(() => {
  const icons = {
    '仪表盘': '📊', '用户管理': '👥', '城市管理': '🏙️',
    '景点管理': '🏔️', '美食管理': '🍜', '酒店管理': '🏨',
    '行程模板': '⭐', '行程订单': '📋', '会话管理': '💬',
    '知识库更新': 'KB'
  }
  return icons[route.meta?.title] || '📊'
})

const mainNavItems = [
  { path: '/dashboard', title: '仪表盘', icon: Odometer },
  { path: '/users', title: '用户管理', icon: User },
  { path: '/conversations', title: '会话管理', icon: ChatLineRound },
  { path: '/agent-runs', title: 'Agent 运行', icon: DataLine }
]

const contentNavItems = [
  { path: '/cities', title: '城市管理', icon: MapLocation },
  { path: '/spots', title: '景点管理', icon: Picture },
  { path: '/foods', title: '美食管理', icon: Dish },
  { path: '/hotels', title: '酒店管理', icon: OfficeBuilding },
  { path: '/templates', title: '行程模板', icon: Collection },
  { path: '/knowledge', title: '知识库更新', icon: DataAnalysis }
]

const orderNavItems = [
  { path: '/trip-plans', title: '行程订单', icon: List }
]

function handleLogout() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  router.push('/login')
}
</script>
