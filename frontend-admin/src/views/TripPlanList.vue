<template>
  <div>
    <div class="table-card">
      <div class="card-header">
        <div class="header-left">
          <h3>📋 行程订单</h3>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索行程标题 / 用户名"
            prefix-icon="Search"
            clearable
            class="admin-search"
            style="width:240px"
            @input="handleSearch"
          />
        </div>
        <div class="header-right">
          <el-tag type="info" effect="plain">共 {{ total }} 条行程</el-tag>
        </div>
      </div>
      <div class="card-body">
        <el-table :data="list" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="nickname" label="用户" width="120" />
          <el-table-column prop="title" label="行程标题" min-width="180" show-overflow-tooltip />
          <el-table-column prop="departureCity" label="出发地" width="100" />
          <el-table-column prop="cityName" label="目的地" width="100" />
          <el-table-column prop="days" label="天数" width="70" align="center" />
          <el-table-column prop="peopleCount" label="人数" width="70" align="center" />
          <el-table-column label="预算等级" width="100">
            <template #default="{ row }">
              <el-tag
                :type="row.budgetLevel === 'HIGH' ? 'danger' : row.budgetLevel === 'MEDIUM' ? 'warning' : 'success'"
                size="small"
                effect="plain"
              >
                {{ row.budgetLevel === 'HIGH' ? '舒适' : row.budgetLevel === 'MEDIUM' ? '适中' : '经济' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="总预算" width="100">
            <template #default="{ row }">¥{{ row.totalBudget }}</template>
          </el-table-column>
          <el-table-column label="生成方式" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.sourceType === 'AI' ? 'success' : 'info'" effect="plain">
                {{ row.sourceType === 'AI' ? 'AI生成' : '规则生成' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">
              <span style="font-size:13px;color:var(--admin-text-muted)">{{ row.createTime }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="viewDetail(row)">详情</el-button>
              <el-popconfirm title="确定删除该行程吗？" @confirm="handleDelete(row.id)">
                <template #reference>
                  <el-button size="small" type="danger" link>删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @change="loadData"
        />
      </div>
    </div>

    <!-- 行程详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="行程详情" size="500px">
      <template v-if="selectedPlan">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="行程ID">{{ selectedPlan.id }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ selectedPlan.title }}</el-descriptions-item>
          <el-descriptions-item label="用户">{{ selectedPlan.nickname || '-' }}</el-descriptions-item>
          <el-descriptions-item label="出发城市">{{ selectedPlan.departureCity }}</el-descriptions-item>
          <el-descriptions-item label="目的地">{{ selectedPlan.cityName || '-' }}</el-descriptions-item>
          <el-descriptions-item label="天数">{{ selectedPlan.days }} 天</el-descriptions-item>
          <el-descriptions-item label="人数">{{ selectedPlan.peopleCount }} 人</el-descriptions-item>
          <el-descriptions-item label="预算等级">
            {{ selectedPlan.budgetLevel === 'HIGH' ? '舒适' : selectedPlan.budgetLevel === 'MEDIUM' ? '适中' : '经济' }}
          </el-descriptions-item>
          <el-descriptions-item label="旅行节奏">
            {{ selectedPlan.pace === 'RELAXED' ? '轻松' : selectedPlan.pace === 'MODERATE' ? '适中' : '紧凑' }}
          </el-descriptions-item>
          <el-descriptions-item label="兴趣标签">{{ selectedPlan.interests || '-' }}</el-descriptions-item>
          <el-descriptions-item label="总预算">¥{{ selectedPlan.totalBudget }}</el-descriptions-item>
          <el-descriptions-item label="生成方式">{{ selectedPlan.sourceType === 'AI' ? 'AI生成' : '规则生成' }}</el-descriptions-item>
          <el-descriptions-item label="简介">{{ selectedPlan.summary || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ selectedPlan.createTime }}</el-descriptions-item>
        </el-descriptions>

        <!-- 行程明细 -->
        <template v-if="selectedPlan.dayPlans?.length">
          <h4 style="margin:20px 0 12px">行程明细</h4>
          <div v-for="day in selectedPlan.dayPlans" :key="day.dayNo" style="margin-bottom:16px;background:#f8faf9;border-radius:12px;padding:14px">
            <div style="font-weight:700;margin-bottom:8px;color:var(--admin-primary-dark)">
              Day {{ day.dayNo }} — {{ day.title }}
            </div>
            <div v-for="item in day.items" :key="item.id" style="display:flex;gap:10px;padding:6px 0;font-size:13px">
              <el-tag size="small" :type="item.itemType === 'SPOT' ? 'primary' : item.itemType === 'FOOD' ? 'warning' : 'success'" effect="plain">
                {{ item.itemType === 'SPOT' ? '景点' : item.itemType === 'FOOD' ? '美食' : item.itemType === 'HOTEL' ? '酒店' : '交通' }}
              </el-tag>
              <span>{{ item.startTime }} {{ item.title }}</span>
              <span style="color:var(--admin-text-muted)">¥{{ item.cost }}</span>
            </div>
          </div>
        </template>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchTripPlans, fetchTripPlan, deleteTripPlan } from '../api/admin.js'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const list = ref([])
const page = ref(1)
const size = ref(10)
const total = ref(0)
const searchKeyword = ref('')
const drawerVisible = ref(false)
const selectedPlan = ref(null)

let searchTimer = null

onMounted(() => { loadData() })

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (searchKeyword.value) params.keyword = searchKeyword.value
    const data = await fetchTripPlans(params)
    list.value = data.records || []
    total.value = data.total || 0
  } catch {
    ElMessage.error('加载行程列表失败')
  }
  loading.value = false
}

function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; loadData() }, 300)
}

async function viewDetail(row) {
  try {
    selectedPlan.value = await fetchTripPlan(row.id)
    drawerVisible.value = true
  } catch {
    selectedPlan.value = row
    drawerVisible.value = true
  }
}

async function handleDelete(id) {
  try {
    await deleteTripPlan(id)
    ElMessage.success('已删除')
    loadData()
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>
