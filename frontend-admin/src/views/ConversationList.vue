<template>
  <div>
    <div class="table-card">
      <div class="card-header">
        <div class="header-left">
          <h3>AI 会话列表</h3>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索用户 / 标题 / 会话 ID"
            prefix-icon="Search"
            clearable
            class="admin-search"
            style="width: 280px"
            @input="handleSearch"
          />
          <el-tag v-if="filteredUserId" closable type="success" effect="plain" @close="clearUserFilter">
            用户：{{ route.query.user || filteredUserId }}
          </el-tag>
        </div>
        <div class="header-right">
          <el-tag type="info" effect="plain">共 {{ total }} 段会话</el-tag>
        </div>
      </div>

      <div class="card-body">
        <el-table :data="conversations" stripe style="width: 100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column label="用户" min-width="145">
            <template #default="{ row }">
              <strong>{{ row.nickname || row.username }}</strong>
              <div class="muted-line">{{ row.username }} · UID {{ row.userId }}</div>
            </template>
          </el-table-column>
          <el-table-column prop="title" label="会话标题" min-width="190" show-overflow-tooltip />
          <el-table-column prop="lastMessagePreview" label="最后消息" min-width="240" show-overflow-tooltip />
          <el-table-column label="消息数" width="90" align="center">
            <template #default="{ row }">{{ row.messageCount }} 条</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag type="success" size="small" effect="plain">{{ row.status === 'ACTIVE' ? '正常' : row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="最后更新" width="170">
            <template #default="{ row }"><span class="muted-line">{{ formatDate(row.updateTime) }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="130" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="viewDetail(row)">查看</el-button>
              <el-popconfirm title="确定删除这段会话吗？" @confirm="removeConversation(row)">
                <template #reference><el-button size="small" type="danger" link>删除</el-button></template>
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
          @change="loadConversations"
        />
      </div>
    </div>

    <el-drawer v-model="drawerVisible" title="会话详情" size="min(620px, 92vw)">
      <template v-if="selectedConversation">
        <el-descriptions :column="1" border class="conversation-meta">
          <el-descriptions-item label="用户">
            {{ selectedConversation.nickname || selectedConversation.username }}
            （{{ selectedConversation.username }} / UID {{ selectedConversation.userId }}）
          </el-descriptions-item>
          <el-descriptions-item label="标题">{{ selectedConversation.title }}</el-descriptions-item>
          <el-descriptions-item label="会话 ID">{{ selectedConversation.conversationId }}</el-descriptions-item>
          <el-descriptions-item label="消息数">{{ selectedConversation.messageCount }} 条</el-descriptions-item>
        </el-descriptions>

        <section class="plan-version-panel">
          <div class="section-heading">
            <h4>关联行程版本</h4>
            <el-tag size="small" type="info" effect="plain">{{ selectedPlanVersions.length }} 个版本</el-tag>
          </div>
          <el-table v-if="selectedPlanVersions.length" :data="selectedPlanVersions" size="small" border>
            <el-table-column label="版本" width="88">
              <template #default="{ row }">V{{ row.planVersion }}</template>
            </el-table-column>
            <el-table-column label="目的地" prop="destination" width="110" />
            <el-table-column label="方案" min-width="190">
              <template #default="{ row }">{{ row.plan?.title || row.planId }}</template>
            </el-table-column>
            <el-table-column label="状态" width="88">
              <template #default="{ row }">
                <el-tag :type="row.current ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.current ? '当前' : '历史' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="保存时间" min-width="155">
              <template #default="{ row }">{{ formatDate(row.createdAt) }}</template>
            </el-table-column>
          </el-table>
          <div v-else class="message-empty compact">该会话尚未保存行程方案</div>
        </section>

        <div class="message-history">
          <h4>消息记录</h4>
          <div v-if="!selectedMessages.length" class="message-empty">这段会话还没有消息</div>
          <div
            v-for="message in selectedMessages"
            :key="message.id"
            class="admin-message"
            :class="message.role === 'USER' ? 'user' : 'assistant'"
          >
            <div class="message-label">
              <strong>{{ message.role === 'USER' ? '用户' : 'AI Agent' }}</strong>
              <span>{{ formatDate(message.createTime) }}</span>
            </div>
            <p>{{ message.content }}</p>
            <div v-if="message.intent || message.status === 'FAILED'" class="message-tags">
              <el-tag v-if="message.intent" size="small" effect="plain">{{ message.intent }}</el-tag>
              <el-tag v-if="message.status === 'FAILED'" size="small" type="danger" effect="plain">失败</el-tag>
            </div>
          </div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { deleteConversation, fetchConversation, fetchConversations } from '../api/admin.js'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const conversations = ref([])
const page = ref(1)
const size = ref(10)
const total = ref(0)
const searchKeyword = ref('')
const filteredUserId = ref(route.query.userId || '')
const drawerVisible = ref(false)
const selectedConversation = ref(null)
const selectedMessages = ref([])
const selectedPlanVersions = ref([])
let searchTimer = null

onMounted(loadConversations)

async function loadConversations() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (searchKeyword.value) params.keyword = searchKeyword.value
    if (filteredUserId.value) params.userId = filteredUserId.value
    const data = await fetchConversations(params)
    conversations.value = data.records || []
    total.value = data.total || 0
  } catch (error) {
    ElMessage.error(error.message || '加载会话列表失败')
    conversations.value = []
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    loadConversations()
  }, 300)
}

async function viewDetail(row) {
  try {
    const data = await fetchConversation(row.id)
    selectedConversation.value = data.conversation
    selectedMessages.value = data.messages || []
    selectedPlanVersions.value = data.planVersions || []
    drawerVisible.value = true
  } catch (error) {
    ElMessage.error(error.message || '加载会话详情失败')
  }
}

async function removeConversation(row) {
  try {
    await deleteConversation(row.id)
    ElMessage.success('会话已删除')
    loadConversations()
  } catch (error) {
    ElMessage.error(error.message || '删除失败')
  }
}

function clearUserFilter() {
  filteredUserId.value = ''
  router.replace({ path: '/conversations' })
  page.value = 1
  loadConversations()
}

function formatDate(value) {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.muted-line {
  margin-top: 3px;
  color: var(--admin-text-muted);
  font-size: 12px;
}

.conversation-meta {
  margin-bottom: 22px;
}

.message-history h4 {
  margin: 0 0 14px;
  font-size: 15px;
}

.plan-version-panel {
  margin-bottom: 22px;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-heading h4 {
  margin: 0;
  font-size: 15px;
}

.message-empty.compact {
  padding: 24px 0;
  border: 1px dashed var(--admin-border);
}

.admin-message {
  max-width: 88%;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: #fff;
}

.admin-message.user {
  margin-left: auto;
  border-color: #bfe8db;
  background: #f0faf6;
}

.message-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: var(--admin-text-muted);
  font-size: 11px;
}

.message-label strong {
  color: var(--admin-text);
  font-size: 12px;
}

.admin-message p {
  margin: 8px 0 0;
  color: var(--admin-text);
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.message-tags {
  display: flex;
  gap: 6px;
  margin-top: 9px;
}

.message-empty {
  padding: 50px 0;
  color: var(--admin-text-muted);
  text-align: center;
}
</style>
