<template>
  <div>
    <div class="table-card">
      <div class="card-header">
        <div class="header-left">
          <h3>👥 用户列表</h3>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索用户名 / 昵称"
            prefix-icon="Search"
            clearable
            class="admin-search"
            style="width:240px"
            @input="handleSearch"
          />
        </div>
        <div class="header-right">
          <el-tag type="info" effect="plain">共 {{ total }} 个用户</el-tag>
        </div>
      </div>
      <div class="card-body">
        <el-table :data="users" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="username" label="用户名" min-width="120" />
          <el-table-column prop="nickname" label="昵称" min-width="120" />
          <el-table-column prop="mobile" label="手机号" width="130" />
          <el-table-column label="角色" width="90">
            <template #default="{ row }">
              <el-tag :type="row.role === 'ADMIN' ? 'warning' : 'info'" size="small" effect="plain">
                {{ row.role === 'ADMIN' ? '管理员' : '用户' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 1 ? 'success' : 'danger'" size="small" effect="plain">
                {{ row.status === 1 ? '正常' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="注册时间" width="170">
            <template #default="{ row }">
              <span style="font-size:13px;color:var(--admin-text-muted)">{{ row.createTime }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="viewDetail(row)">详情</el-button>
              <el-popconfirm
                :title="row.status === 1 ? '确定要禁用该用户吗？' : '确定要启用该用户吗？'"
                @confirm="toggleStatus(row)"
              >
                <template #reference>
                  <el-button size="small" :type="row.status === 1 ? 'danger' : 'success'" link>
                    {{ row.status === 1 ? '禁用' : '启用' }}
                  </el-button>
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
          @change="loadUsers"
        />
      </div>
    </div>

    <!-- 用户详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="用户详情" size="400px">
      <template v-if="selectedUser">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="ID">{{ selectedUser.id }}</el-descriptions-item>
          <el-descriptions-item label="用户名">{{ selectedUser.username }}</el-descriptions-item>
          <el-descriptions-item label="昵称">{{ selectedUser.nickname || '-' }}</el-descriptions-item>
          <el-descriptions-item label="手机号">{{ selectedUser.mobile || '-' }}</el-descriptions-item>
          <el-descriptions-item label="角色">
            <el-tag :type="selectedUser.role === 'ADMIN' ? 'warning' : 'info'" size="small" effect="plain">
              {{ selectedUser.role === 'ADMIN' ? '管理员' : '用户' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="selectedUser.status === 1 ? 'success' : 'danger'" size="small" effect="plain">
              {{ selectedUser.status === 1 ? '正常' : '禁用' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="注册时间">{{ selectedUser.createTime }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchUsers, fetchUser, updateUserStatus } from '../api/admin.js'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const users = ref([])
const page = ref(1)
const size = ref(10)
const total = ref(0)
const searchKeyword = ref('')
const drawerVisible = ref(false)
const selectedUser = ref(null)

let searchTimer = null

onMounted(() => { loadUsers() })

async function loadUsers() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (searchKeyword.value) params.keyword = searchKeyword.value
    const data = await fetchUsers(params)
    users.value = data.records || []
    total.value = data.total || 0
  } catch {
    ElMessage.error('加载用户列表失败')
    users.value = []
  }
  loading.value = false
}

function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadUsers()
  }, 300)
}

async function viewDetail(row) {
  try {
    selectedUser.value = await fetchUser(row.id)
    drawerVisible.value = true
  } catch {
    // 降级：使用列表数据
    selectedUser.value = row
    drawerVisible.value = true
  }
}

async function toggleStatus(row) {
  const newStatus = row.status === 1 ? 0 : 1
  try {
    await updateUserStatus(row.id, newStatus)
    row.status = newStatus
    ElMessage.success(newStatus === 1 ? '已启用' : '已禁用')
  } catch {
    ElMessage.error('操作失败')
  }
}
</script>
