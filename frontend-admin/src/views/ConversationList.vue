<template>
  <div>
    <div class="table-card">
      <div class="card-header">
        <div class="header-left">
          <h3>💬 会话管理</h3>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索会话ID / 用户ID / 标题"
            prefix-icon="Search"
            clearable
            class="admin-search"
            style="width:240px"
            @input="handleSearch"
          />
          <el-select v-model="statusFilter" clearable placeholder="全部状态" style="width:130px" @change="handleFilter">
            <el-option label="活跃" value="ACTIVE" />
            <el-option label="完成" value="COMPLETED" />
            <el-option label="错误" value="ERROR" />
          </el-select>
        </div>
        <div class="header-right">
          <el-tag type="info" effect="plain">共 {{ total }} 条会话</el-tag>
        </div>
      </div>
      <div class="card-body">
        <el-table :data="list" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="conversationId" label="会话ID" width="200" show-overflow-tooltip />
          <el-table-column prop="userId" label="用户ID" width="100" />
          <el-table-column prop="title" label="会话标题" min-width="180" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag
                :type="row.status === 'ACTIVE' ? 'success' : row.status === 'ERROR' ? 'danger' : 'info'"
                size="small"
                effect="plain"
              >
                {{ row.status === 'ACTIVE' ? '活跃' : row.status === 'ERROR' ? '错误' : '完成' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="lastMessagePreview" label="最后消息预览" min-width="200" show-overflow-tooltip />
          <el-table-column prop="messageCount" label="消息数" width="90" align="center" />
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">
              <span style="font-size:13px;color:var(--admin-text-muted)">{{ row.createTime }}</span>
            </template>
          </el-table-column>
          <el-table-column label="更新时间" width="170">
            <template #default="{ row }">
              <span style="font-size:13px;color:var(--admin-text-muted)">{{ row.updateTime }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="viewDetail(row)">详情</el-button>
              <el-popconfirm title="确定删除该会话吗？" @confirm="handleDelete(row.id)">
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

    <!-- 会话详情抽屉 -->
    <el-drawer v-model="drawerVisible" title="会话详情" size="620px">
      <template v-if="selectedConversation">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="会话ID">{{ selectedConversation.conversationId }}</el-descriptions-item>
          <el-descriptions-item label="用户ID">{{ selectedConversation.userId }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ selectedConversation.title }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag
              :type="selectedConversation.status === 'ACTIVE' ? 'success' : selectedConversation.status === 'ERROR' ? 'danger' : 'info'"
              size="small"
              effect="plain"
            >
              {{ selectedConversation.status === 'ACTIVE' ? '活跃' : selectedConversation.status === 'ERROR' ? '错误' : '完成' }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="消息数量">{{ selectedConversation.messageCount }}</el-descriptions-item>
          <el-descriptions-item label="最后消息预览">{{ selectedConversation.lastMessagePreview || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ selectedConversation.createTime }}</el-descriptions-item>
          <el-descriptions-item label="更新时间">{{ selectedConversation.updateTime }}</el-descriptions-item>
        </el-descriptions>
        <el-divider content-position="left">消息记录</el-divider>
        <div v-loading="detailLoading" class="message-timeline">
          <el-empty v-if="!selectedConversation.messages?.length" description="暂无消息" :image-size="72" />
          <div
            v-for="message in selectedConversation.messages || []"
            :key="message.id"
            class="message-item"
            :class="message.role === 'USER' ? 'is-user' : 'is-assistant'"
          >
            <div class="message-meta">
              <el-tag size="small" :type="message.role === 'USER' ? 'primary' : 'success'">
                {{ message.role === 'USER' ? '用户' : 'AI 助手' }}
              </el-tag>
              <el-tag v-if="message.intent" size="small" type="info" effect="plain">{{ message.intent }}</el-tag>
              <el-tag v-if="message.status === 'FAILED'" size="small" type="danger">失败</el-tag>
              <span>{{ message.createTime }}</span>
            </div>
            <p>{{ message.content }}</p>
            <small v-if="message.hasAgentState">包含结构化 Agent 状态（已隐藏敏感原文）</small>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchConversations, fetchConversation, deleteConversation } from '../api/admin.js'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const list = ref([])
const page = ref(1)
const size = ref(10)
const total = ref(0)
const searchKeyword = ref('')
const statusFilter = ref('')
const drawerVisible = ref(false)
const selectedConversation = ref(null)
const detailLoading = ref(false)

let searchTimer = null

onMounted(() => { loadData() })

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (searchKeyword.value) params.keyword = searchKeyword.value
    if (statusFilter.value) params.status = statusFilter.value
    const data = await fetchConversations(params)
    list.value = data.records || []
    total.value = data.total || 0
  } catch {
    ElMessage.error('加载会话列表失败')
  }
  loading.value = false
}

function handleFilter() {
  page.value = 1
  loadData()
}

function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; loadData() }, 300)
}

async function viewDetail(row) {
  selectedConversation.value = { ...row, messages: [] }
  drawerVisible.value = true
  detailLoading.value = true
  try {
    selectedConversation.value = await fetchConversation(row.id)
  } catch {
    ElMessage.error('加载会话详情失败')
  } finally {
    detailLoading.value = false
  }
}

async function handleDelete(id) {
  try {
    await deleteConversation(id)
    ElMessage.success('已删除')
    loadData()
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>

<style scoped>
.message-timeline { display: grid; gap: 14px; min-height: 120px; }
.message-item { padding: 14px 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 12px; background: var(--el-fill-color-light); }
.message-item.is-user { border-left: 3px solid var(--el-color-primary); }
.message-item.is-assistant { border-left: 3px solid var(--el-color-success); }
.message-meta { display: flex; align-items: center; gap: 8px; color: var(--admin-text-muted); font-size: 12px; }
.message-item p { margin: 10px 0 0; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.message-item small { display: block; margin-top: 8px; color: var(--admin-text-muted); }
</style>
