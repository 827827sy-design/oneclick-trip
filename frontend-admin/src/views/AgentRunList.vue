<template>
  <div class="run-page">
    <section class="metric-strip">
      <div class="metric-item">
        <span>累计运行</span>
        <strong>{{ stats.total || 0 }}</strong>
      </div>
      <div class="metric-item">
        <span>完成率</span>
        <strong>{{ stats.completionRate || 0 }}%</strong>
      </div>
      <div class="metric-item">
        <span>平均耗时</span>
        <strong>{{ formatDuration(stats.averageDurationMs) }}</strong>
      </div>
      <div class="metric-item alert">
        <span>工具异常率</span>
        <strong>{{ stats.toolErrorRate || 0 }}%</strong>
      </div>
      <div class="metric-item warning">
        <span>降级运行率</span>
        <strong>{{ stats.degradationRate || 0 }}%</strong>
      </div>
    </section>

    <div class="table-card">
      <div class="card-header filter-header">
        <div>
          <h3>Agent 运行记录</h3>
          <p>查看路由结果、节点耗时、工具错误与降级状态</p>
        </div>
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
      </div>

      <div class="filter-bar">
        <el-input
          v-model="filters.keyword"
          clearable
          placeholder="用户 / 会话 ID / 运行 ID"
          :prefix-icon="Search"
          @keyup.enter="search"
        />
        <el-select v-model="filters.intent" clearable placeholder="全部意图">
          <el-option v-for="item in intentOptions" :key="item" :label="intentLabel(item)" :value="item" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="全部状态">
          <el-option label="已完成" value="COMPLETED" />
          <el-option label="失败" value="FAILED" />
        </el-select>
        <el-date-picker
          v-model="filters.timeRange"
          type="datetimerange"
          value-format="YYYY-MM-DDTHH:mm:ss"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
        />
        <el-button type="primary" :icon="Search" @click="search">筛选</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <div class="card-body">
        <el-table :data="runs" stripe v-loading="loading" @row-click="openDetail">
          <el-table-column label="用户" min-width="145">
            <template #default="{ row }">
              <strong>{{ row.nickname || row.username || '未知用户' }}</strong>
              <div class="subline">{{ row.username || '-' }} · UID {{ row.userId }}</div>
            </template>
          </el-table-column>
          <el-table-column label="意图" min-width="130">
            <template #default="{ row }">{{ intentLabel(row.intent) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="92">
            <template #default="{ row }">
              <el-tag :type="row.status === 'COMPLETED' ? 'success' : 'danger'" effect="plain" size="small">
                {{ row.status === 'COMPLETED' ? '已完成' : '失败' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="模型模式" min-width="105" prop="modelMode" />
          <el-table-column label="工具" width="76" align="center">
            <template #default="{ row }">{{ row.selectedTools?.length || 0 }}</template>
          </el-table-column>
          <el-table-column label="异常" width="76" align="center">
            <template #default="{ row }">
              <span :class="{ dangerText: row.toolErrors?.length }">{{ row.toolErrors?.length || 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="降级" width="76" align="center">
            <template #default="{ row }">
              <span :class="{ warningText: row.degradationModes?.length }">{{ row.degradationModes?.length || 0 }}</span>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="105">
            <template #default="{ row }">{{ formatDuration(row.durationMs) }}</template>
          </el-table-column>
          <el-table-column label="执行时间" min-width="165">
            <template #default="{ row }"><span class="subline">{{ formatDate(row.createTime) }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="86" fixed="right">
            <template #default="{ row }">
              <el-button type="primary" link @click.stop="openDetail(row)">排查</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          @change="loadRuns"
        />
      </div>
    </div>

    <el-drawer v-model="drawerVisible" title="Agent 运行排查" size="min(680px, 94vw)">
      <template v-if="selectedRun">
        <el-alert
          v-if="selectedRun.status === 'FAILED'"
          type="error"
          :closable="false"
          show-icon
          :title="selectedRun.errorCode || 'AGENT_RUN_FAILED'"
          :description="selectedRun.errorMessage || '运行未完成，请结合节点耗时与工具错误排查。'"
        />
        <el-alert
          v-else-if="selectedRun.degradationModes?.length"
          type="warning"
          :closable="false"
          show-icon
          title="本次运行已完成，但使用了降级结果"
          description="建议在正式展示前确认相应实时接口或大模型服务可用。"
        />

        <el-descriptions :column="2" border class="run-meta">
          <el-descriptions-item label="运行 ID" :span="2">{{ selectedRun.runId }}</el-descriptions-item>
          <el-descriptions-item label="会话 ID" :span="2">{{ selectedRun.conversationId }}</el-descriptions-item>
          <el-descriptions-item label="用户">{{ selectedRun.nickname || selectedRun.username }}</el-descriptions-item>
          <el-descriptions-item label="意图">{{ intentLabel(selectedRun.intent) }}</el-descriptions-item>
          <el-descriptions-item label="模型模式">{{ selectedRun.modelMode }}</el-descriptions-item>
          <el-descriptions-item label="总耗时">{{ formatDuration(selectedRun.durationMs) }}</el-descriptions-item>
          <el-descriptions-item label="下一动作">{{ selectedRun.nextAction || '-' }}</el-descriptions-item>
          <el-descriptions-item label="方案保存">{{ selectedRun.planSaved ? '是' : '否' }}</el-descriptions-item>
        </el-descriptions>

        <section class="detail-section">
          <h4>节点耗时</h4>
          <div v-if="!nodeTimingRows.length" class="empty-line">暂无节点遥测数据</div>
          <div v-for="node in nodeTimingRows" :key="node.name" class="timing-row">
            <span>{{ nodeLabel(node.name) }}</span>
            <el-progress :percentage="node.percentage" :show-text="false" :stroke-width="8" />
            <strong>{{ formatDuration(node.duration) }}</strong>
          </div>
        </section>

        <section class="detail-section">
          <h4>调用工具</h4>
          <div class="tag-list">
            <el-tag v-for="tool in selectedRun.selectedTools || []" :key="tool" effect="plain">{{ tool }}</el-tag>
            <span v-if="!selectedRun.selectedTools?.length" class="empty-line">本次未调用工具</span>
          </div>
        </section>

        <section v-if="selectedRun.toolErrors?.length" class="detail-section">
          <h4>工具错误</h4>
          <div v-for="error in selectedRun.toolErrors" :key="`${error.toolName}-${error.attempt}`" class="issue-row danger">
            <strong>{{ error.toolName }}</strong>
            <span>{{ error.errorCode }} · 第 {{ error.attempt }} 次 · {{ error.retryable ? '可重试' : '不可重试' }}</span>
          </div>
        </section>

        <section v-if="selectedRun.degradationModes?.length" class="detail-section">
          <h4>降级状态</h4>
          <div v-for="item in selectedRun.degradationModes" :key="`${item.component}-${item.mode}`" class="issue-row warning">
            <strong>{{ item.component }}</strong>
            <span>{{ item.mode }} · {{ item.source }}</span>
          </div>
        </section>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import { fetchAgentRun, fetchAgentRuns, fetchAgentRunStats } from '../api/admin.js'

const intentOptions = ['trip_plan', 'modify_plan', 'weather_query', 'hotel_query', 'transport_query', 'general_qa', 'booking', 'memory_manage']
const intentLabels = {
  trip_plan: '完整行程规划', modify_plan: '修改行程', weather_query: '天气查询',
  hotel_query: '酒店查询', transport_query: '交通查询', general_qa: '旅游问答',
  booking: '预订', memory_manage: '偏好管理', unknown: '未知'
}
const nodeLabels = {
  recognize_intent: '意图识别', normalize_state: '状态整理', supervisor: '总控路由',
  phase1_research: '第一阶段研究', candidate_selection: '候选筛选',
  phase2_research: '第二阶段研究', plan_trip: '行程生成', hard_validate: '硬校验',
  review_plan: '软评审', revise_plan: '方案修订', save_plan: '保存版本'
}

const loading = ref(false)
const runs = ref([])
const stats = ref({})
const page = ref(1)
const size = ref(20)
const total = ref(0)
const drawerVisible = ref(false)
const selectedRun = ref(null)
const filters = reactive({ keyword: '', intent: '', status: '', timeRange: [] })

const nodeTimingRows = computed(() => {
  const entries = Object.entries(selectedRun.value?.nodeTimings || {})
    .map(([name, duration]) => ({ name, duration: Number(duration) || 0 }))
    .sort((a, b) => b.duration - a.duration)
  const max = Math.max(...entries.map(item => item.duration), 1)
  return entries.map(item => ({ ...item, percentage: Math.max(2, Math.round(item.duration * 100 / max)) }))
})

onMounted(reload)

async function reload() {
  await Promise.all([loadStats(), loadRuns()])
}

async function loadStats() {
  try {
    stats.value = await fetchAgentRunStats() || {}
  } catch (error) {
    ElMessage.error(error.message || '加载运行指标失败')
  }
}

async function loadRuns() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.intent) params.intent = filters.intent
    if (filters.status) params.status = filters.status
    if (filters.timeRange?.length === 2) {
      params.startTime = filters.timeRange[0]
      params.endTime = filters.timeRange[1]
    }
    const data = await fetchAgentRuns(params)
    runs.value = data?.records || []
    total.value = data?.total || 0
  } catch (error) {
    runs.value = []
    ElMessage.error(error.message || '加载 Agent 运行记录失败')
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  loadRuns()
}

function resetFilters() {
  Object.assign(filters, { keyword: '', intent: '', status: '', timeRange: [] })
  search()
}

async function openDetail(row) {
  try {
    selectedRun.value = await fetchAgentRun(row.id)
    drawerVisible.value = true
  } catch (error) {
    ElMessage.error(error.message || '加载运行详情失败')
  }
}

function formatDuration(value) {
  const ms = Number(value)
  if (!Number.isFinite(ms)) return '-'
  if (ms < 1000) return `${ms} ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`
  return `${Math.floor(ms / 60000)}m ${Math.round(ms % 60000 / 1000)}s`
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
}

function intentLabel(value) {
  return intentLabels[value] || value || '未知'
}

function nodeLabel(value) {
  return nodeLabels[value] || value
}
</script>

<style scoped>
.run-page { display: grid; gap: 16px; }
.metric-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); border: 1px solid var(--admin-border); background: #fff; }
.metric-item { min-width: 0; padding: 18px 20px; border-right: 1px solid var(--admin-border); }
.metric-item:last-child { border-right: 0; }
.metric-item span { display: block; color: var(--admin-text-muted); font-size: 12px; }
.metric-item strong { display: block; margin-top: 8px; color: var(--admin-text); font-size: 24px; line-height: 1; }
.metric-item.alert strong { color: #c2413c; }
.metric-item.warning strong { color: #ad6800; }
.filter-header p { margin: 5px 0 0; color: var(--admin-text-muted); font-size: 12px; }
.filter-bar { display: grid; grid-template-columns: minmax(220px, 1fr) 150px 130px minmax(320px, 1.4fr) auto auto; gap: 10px; padding: 14px 18px; border-top: 1px solid var(--admin-border); border-bottom: 1px solid var(--admin-border); background: #fafcfb; }
.subline { margin-top: 3px; color: var(--admin-text-muted); font-size: 12px; }
.dangerText { color: #c2413c; font-weight: 700; }
.warningText { color: #ad6800; font-weight: 700; }
.run-meta { margin: 18px 0 22px; }
.detail-section { padding: 18px 0; border-top: 1px solid var(--admin-border); }
.detail-section h4 { margin: 0 0 13px; font-size: 14px; }
.timing-row { display: grid; grid-template-columns: minmax(125px, 1fr) minmax(180px, 2fr) 76px; gap: 12px; align-items: center; margin: 10px 0; font-size: 12px; }
.timing-row strong { text-align: right; }
.tag-list { display: flex; flex-wrap: wrap; gap: 8px; }
.issue-row { display: flex; justify-content: space-between; gap: 16px; margin: 8px 0; padding: 11px 12px; border-left: 3px solid; background: #fafafa; font-size: 12px; }
.issue-row span { color: var(--admin-text-muted); text-align: right; }
.issue-row.danger { border-color: #c2413c; background: #fff6f5; }
.issue-row.warning { border-color: #d48806; background: #fffaf0; }
.empty-line { color: var(--admin-text-muted); font-size: 12px; }
@media (max-width: 1100px) {
  .metric-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .metric-item { border-bottom: 1px solid var(--admin-border); }
  .filter-bar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
