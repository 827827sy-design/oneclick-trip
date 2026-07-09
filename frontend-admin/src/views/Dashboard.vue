<template>
  <div>
    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon teal">👥</div>
        <div class="stat-info">
          <h3>{{ dashboard.totalUsers ?? '-' }}</h3>
          <p>注册用户</p>
          <span class="stat-trend up">📈 总用户数</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon blue">🏙️</div>
        <div class="stat-info">
          <h3>{{ dashboard.totalCities ?? '-' }}</h3>
          <p>收录城市</p>
          <span class="stat-trend up">📈 目的地覆盖</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon orange">📋</div>
        <div class="stat-info">
          <h3>{{ dashboard.totalPlans ?? '-' }}</h3>
          <p>生成行程</p>
          <span class="stat-trend up">📈 累计规划</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon green">🏔️</div>
        <div class="stat-info">
          <h3>{{ dashboard.totalSpots ?? '-' }}</h3>
          <p>收录景点</p>
          <span class="stat-trend up">📈 内容资产</span>
        </div>
      </div>
    </div>

    <!-- 最近行程 -->
    <div class="table-card" style="margin-bottom:24px">
      <div class="card-header">
        <div class="header-left">
          <h3>📋 最近行程</h3>
        </div>
        <div class="header-right">
          <el-button size="small" @click="router.push('/trip-plans')">查看全部</el-button>
        </div>
      </div>
      <div class="card-body">
        <el-table :data="recentPlans" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="nickname" label="用户" min-width="100" />
          <el-table-column prop="title" label="行程标题" min-width="180" />
          <el-table-column prop="cityName" label="目的地" width="100" />
          <el-table-column prop="days" label="天数" width="70" />
          <el-table-column label="预算" width="120">
            <template #default="{ row }">
              <el-tag size="small" type="warning" effect="plain">
                {{ row.budgetLevel === 'HIGH' ? '舒适' : row.budgetLevel === 'MEDIUM' ? '适中' : '经济' }}
              </el-tag>
              <span style="margin-left:6px;font-size:13px">¥{{ row.totalBudget }}</span>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">
              <span style="font-size:13px;color:var(--admin-text-muted)">{{ row.createTime }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 快速入口 -->
    <div class="table-card">
      <div class="card-header">
        <h3>⚡ 快捷操作</h3>
      </div>
      <div class="card-body" style="padding:20px 24px">
        <div style="display:flex;gap:12px;flex-wrap:wrap">
          <el-button class="admin-btn-primary" @click="router.push('/cities')">
            🏙️ 管理城市
          </el-button>
          <el-button class="admin-btn-primary" style="background:linear-gradient(135deg,#ff6b35,#ff8c5a)!important;box-shadow:0 4px 14px rgba(255,107,53,0.24)!important" @click="router.push('/spots')">
            🏔️ 管理景点
          </el-button>
          <el-button class="admin-btn-primary" style="background:linear-gradient(135deg,#4facfe,#00f2fe)!important;box-shadow:0 4px 14px rgba(79,172,254,0.24)!important" @click="router.push('/foods')">
            🍜 管理美食
          </el-button>
          <el-button class="admin-btn-primary" style="background:linear-gradient(135deg,#f093fb,#f5576c)!important;box-shadow:0 4px 14px rgba(240,147,251,0.24)!important" @click="router.push('/hotels')">
            🏨 管理酒店
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDashboard, fetchTripPlans } from '../api/admin.js'

const router = useRouter()
const loading = ref(false)
const dashboard = ref({})
const recentPlans = ref([])

onMounted(async () => {
  loading.value = true
  try {
    dashboard.value = await fetchDashboard()
  } catch {
    // 后端未就绪时使用占位数据
    dashboard.value = {
      totalUsers: 0,
      totalCities: 0,
      totalPlans: 0,
      totalSpots: 0
    }
  }

  try {
    const data = await fetchTripPlans({ page: 1, size: 5 })
    recentPlans.value = data.records || []
  } catch {
    recentPlans.value = []
  }
  loading.value = false
})
</script>
