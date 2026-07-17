import { createRouter, createWebHashHistory } from 'vue-router'

const TOKEN_KEY = 'oneclick_trip_token'
const USER_KEY = 'oneclick_trip_user'

function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY))
  } catch {
    return null
  }
}

const routes = [
  {
    path: '/',
    component: () => import('../layouts/AdminLayout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '仪表盘', icon: 'Odometer' }
      },
      {
        path: 'users',
        name: 'UserList',
        component: () => import('../views/UserList.vue'),
        meta: { title: '用户管理', icon: 'User' }
      },
      {
        path: 'conversations',
        name: 'ConversationList',
        component: () => import('../views/ConversationList.vue'),
        meta: { title: '会话管理', icon: 'ChatLineRound' }
      },
      {
        path: 'cities',
        name: 'CityList',
        component: () => import('../views/CityList.vue'),
        meta: { title: '城市管理', icon: 'MapLocation' }
      },
      {
        path: 'spots',
        name: 'SpotList',
        component: () => import('../views/SpotList.vue'),
        meta: { title: '景点管理', icon: 'Picture' }
      },
      {
        path: 'foods',
        name: 'FoodList',
        component: () => import('../views/FoodList.vue'),
        meta: { title: '美食管理', icon: 'Dish' }
      },
      {
        path: 'hotels',
        name: 'HotelList',
        component: () => import('../views/HotelList.vue'),
        meta: { title: '酒店管理', icon: 'OfficeBuilding' }
      },
      {
        path: 'templates',
        name: 'TripTemplateList',
        component: () => import('../views/TripTemplateList.vue'),
        meta: { title: '行程模板', icon: 'Collection' }
      },
      {
        path: 'trip-plans',
        name: 'TripPlanList',
        component: () => import('../views/TripPlanList.vue'),
        meta: { title: '行程订单', icon: 'List' }
      }
    ]
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { title: '管理员登录' }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard'
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const token = getToken()
  const user = getUser()

  if (to.path === '/login') {
    if (token && user?.role === 'ADMIN') {
      next('/dashboard')
    } else {
      next()
    }
    return
  }

  if (!token) {
    next('/login')
    return
  }

  if (user?.role !== 'ADMIN') {
    next('/login')
    return
  }

  next()
})

export default router
