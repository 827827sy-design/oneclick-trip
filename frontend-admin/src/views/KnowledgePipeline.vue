<template>
  <div class="knowledge-page" v-loading="loading">
    <section class="knowledge-summary">
      <div class="summary-copy">
        <p class="eyebrow">B-02 · 后台知识加工</p>
        <h2>旅游知识库更新工作台</h2>
        <p>管理员采集或录入资料，经 Pandas 清洗、去重和质量检查后，审核发布到 Chroma。</p>
      </div>
      <div class="summary-actions">
        <el-button :icon="Refresh" :loading="rebuilding" @click="rebuildIndex">重建索引</el-button>
        <el-button :icon="Refresh" circle title="刷新数据" @click="loadOverview" />
      </div>
    </section>

    <div class="metric-grid">
      <div class="metric-item">
        <span>向量文档</span>
        <strong>{{ stats.total_documents ?? 0 }}</strong>
        <small>已进入检索库</small>
      </div>
      <div class="metric-item">
        <span>清洗批次</span>
        <strong>{{ stats.batch_count ?? 0 }}</strong>
        <small>保留审核记录</small>
      </div>
      <div class="metric-item pending">
        <span>待发布</span>
        <strong>{{ stats.previewed_batches ?? 0 }}</strong>
        <small>需要人工确认</small>
      </div>
      <div class="metric-item rejected">
        <span>已驳回</span>
        <strong>{{ stats.rejected_batches ?? 0 }}</strong>
        <small>未进入检索库</small>
      </div>
      <div class="metric-item published">
        <span>已发布</span>
        <strong>{{ stats.published_batches ?? 0 }}</strong>
        <small>可供 Agent 检索</small>
      </div>
    </div>

    <section class="workspace-panel">
      <div class="panel-heading">
        <div>
          <h3>新建资料批次</h3>
          <p>离线采集只在管理端触发，用户端 Agent 不会直接调用 Agent Reach。</p>
        </div>
        <el-segmented v-model="inputMode" :options="modeOptions" />
      </div>

      <div v-if="inputMode === 'manual'" class="manual-workspace">
        <el-form label-position="top" class="record-form">
          <div class="form-grid">
            <el-form-item label="城市">
              <el-input v-model="draft.city" placeholder="例如：成都" />
            </el-form-item>
            <el-form-item label="知识类型">
              <el-select v-model="draft.category" style="width: 100%">
                <el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="来源等级">
              <el-select v-model="draft.source_tier" style="width: 100%">
                <el-option label="官方来源" value="official" />
                <el-option label="可信编辑" value="trusted" />
                <el-option label="商业平台" value="commercial" />
                <el-option label="社区内容" value="community" />
              </el-select>
            </el-form-item>
            <el-form-item label="来源名称">
              <el-input v-model="draft.source" placeholder="官网、编辑整理等" />
            </el-form-item>
          </div>
          <el-form-item label="标题">
            <el-input v-model="draft.title" placeholder="资料标题" />
          </el-form-item>
          <el-form-item label="来源链接">
            <el-input v-model="draft.source_url" placeholder="https://...（可选）" />
          </el-form-item>
          <el-form-item label="正文">
            <el-input v-model="draft.content" type="textarea" :rows="4" placeholder="开放时间、游玩建议、交通方式等可核验信息" />
          </el-form-item>
          <el-form-item label="标签">
            <el-input v-model="draft.tagsText" placeholder="亲子、自然、徒步（用逗号分隔）" />
          </el-form-item>
          <div class="form-actions">
            <el-button @click="fillDemo">填入演示资料</el-button>
            <el-button :icon="Plus" @click="addRecord">加入待清洗列表</el-button>
            <el-button type="primary" :icon="DataAnalysis" :disabled="records.length === 0" :loading="previewing" @click="runPreview">
              Pandas 清洗预览
            </el-button>
          </div>
        </el-form>

        <div class="pending-list">
          <div class="list-title">
            <strong>待清洗资料</strong>
            <el-tag effect="plain">{{ records.length }} 条</el-tag>
          </div>
          <el-empty v-if="records.length === 0" description="先录入资料，或使用演示资料" :image-size="72" />
          <div v-else class="record-items">
            <div v-for="(item, index) in records" :key="`${item.title}-${index}`" class="record-item">
              <div>
                <strong>{{ item.title }}</strong>
                <p>{{ item.city }} · {{ item.category }} · {{ sourceTierLabel(item.source_tier) }}</p>
              </div>
              <el-button :icon="Delete" text circle title="移除" @click="records.splice(index, 1)" />
            </div>
          </div>
        </div>
      </div>

      <el-form v-else label-position="top" class="collector-form">
        <el-alert title="离线采集区" description="该操作供管理员更新知识库。采集结果只生成待审核批次，不会自动进入用户检索链路。" type="info" :closable="false" show-icon />
        <div class="form-grid collection-grid">
          <el-form-item label="目的地">
            <el-input v-model="collection.destination" placeholder="成都" />
          </el-form-item>
          <el-form-item label="知识类型">
            <el-select v-model="collection.category" style="width: 100%" @change="syncCollectionBase">
              <el-option v-for="item in categoryOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="采集主题" class="query-field">
            <el-input v-model="collection.query" placeholder="例如：成都适合亲子旅行的景点攻略" />
          </el-form-item>
        </div>
        <el-button type="primary" :icon="Search" :loading="collecting" @click="runCollection">采集并生成审核批次</el-button>
      </el-form>
    </section>

    <section v-if="activeBatch" class="review-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">批次 {{ activeBatch.batch_id }}</p>
          <h3>质量报告与人工审核</h3>
        </div>
        <div class="review-actions">
          <el-tag :type="batchTagType(activeBatch.status)">
            {{ statusLabel(activeBatch.status) }}
          </el-tag>
          <el-button
            v-if="activeBatch.status === 'PREVIEWED'"
            type="danger"
            plain
            :icon="CircleClose"
            :loading="rejectingBatch"
            @click="rejectActiveBatch"
          >驳回批次</el-button>
          <el-button
            v-if="activeBatch.status === 'REJECTED'"
            :icon="RefreshLeft"
            :loading="reopeningBatch"
            @click="reopenActiveBatch"
          >恢复审核</el-button>
          <el-button
            v-if="activeBatch.status === 'PREVIEWED'"
            type="primary"
            :icon="UploadFilled"
            :loading="publishing"
            :disabled="eligibleReviewCount === 0"
            @click="publishActiveBatch"
          >审核通过并发布</el-button>
        </div>
      </div>

      <div class="quality-strip">
        <div><span>输入</span><strong>{{ activeBatch.report.input_count }}</strong></div>
        <div><span>通过清洗</span><strong>{{ activeBatch.report.cleaned_count }}</strong></div>
        <div><span>自动拒绝</span><strong>{{ activeBatch.report.rejected_count }}</strong></div>
        <div><span>人工拒绝</span><strong>{{ activeBatch.manual_rejected_count ?? 0 }}</strong></div>
        <div><span>已删除</span><strong>{{ activeBatch.deleted_record_count ?? 0 }}</strong></div>
        <div><span>重复</span><strong>{{ activeBatch.report.duplicate_count }}</strong></div>
        <div><span>平均质量</span><strong>{{ percent(activeBatch.report.average_quality_score) }}</strong></div>
        <div><span>官方来源</span><strong>{{ percent(activeBatch.report.official_source_rate) }}</strong></div>
      </div>

      <el-tabs v-model="reviewTab">
        <el-tab-pane :label="`清洗通过（${activeBatch.records.length}）`" name="cleaned">
          <el-table :data="activeBatch.records" stripe>
            <el-table-column prop="title" label="标题" min-width="190" />
            <el-table-column label="人工审核" width="110">
              <template #default="{ row }">
                <el-tag :type="recordTagType(row.review_status)" effect="plain">
                  {{ recordStatusLabel(row.review_status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="city" label="城市" width="90" />
            <el-table-column prop="category" label="类型" width="90" />
            <el-table-column label="来源" min-width="140">
              <template #default="{ row }">
                <div>{{ row.source }}</div>
                <small class="muted">{{ sourceTierLabel(row.source_tier) }}</small>
              </template>
            </el-table-column>
            <el-table-column label="质量" width="110">
              <template #default="{ row }">
                <el-progress :percentage="Math.round(row.quality_score * 100)" :stroke-width="7" />
              </template>
            </el-table-column>
            <el-table-column label="资料摘要" min-width="300">
              <template #default="{ row }">
                <div class="content-preview">
                  <p>{{ row.content }}</p>
                  <el-button link type="primary" :icon="View" @click="openRecordDetails(row)">
                    查看全文
                  </el-button>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="审核操作" width="190" fixed="right">
              <template #default="{ row }">
                <div class="record-review-actions">
                  <el-button
                    v-if="activeBatch.status === 'PREVIEWED' && row.review_status !== 'APPROVED'"
                    link
                    type="success"
                    :icon="CircleCheck"
                    :loading="reviewingRecordId === row.record_id"
                    @click="approveRecord(row)"
                  >通过</el-button>
                  <el-button
                    v-if="activeBatch.status === 'PREVIEWED' && row.review_status !== 'REJECTED'"
                    link
                    type="danger"
                    :icon="CircleClose"
                    :loading="reviewingRecordId === row.record_id"
                    @click="rejectRecord(row)"
                  >拒绝</el-button>
                  <el-button
                    v-if="activeBatch.status === 'PREVIEWED' && row.review_status === 'REJECTED'"
                    link
                    :icon="RefreshLeft"
                    :loading="reviewingRecordId === row.record_id"
                    @click="restoreRecord(row)"
                  >恢复</el-button>
                  <el-button
                    v-if="row.review_status === 'APPROVED' && activeBatch.status !== 'REJECTED'"
                    link
                    type="danger"
                    :icon="Delete"
                    :loading="deletingRecordId === row.record_id"
                    @click="deleteApprovedRecord(row)"
                  >删除</el-button>
                </div>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane :label="`自动拒绝（${activeBatch.rejected.length}）`" name="rejected">
          <el-table :data="activeBatch.rejected" stripe>
            <el-table-column prop="row_index" label="原行号" width="90" />
            <el-table-column prop="title" label="标题" min-width="200" />
            <el-table-column label="拒绝原因" min-width="260">
              <template #default="{ row }">
                <el-tag v-for="reason in row.reasons" :key="reason" type="danger" effect="plain" class="reason-tag">
                  {{ rejectionLabel(reason) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane :label="`删除记录（${activeBatch.deleted_record_count ?? 0}）`" name="deleted">
          <el-empty v-if="!activeBatch.deleted_records?.length" description="暂无已删除资料" :image-size="64" />
          <el-table v-else :data="activeBatch.deleted_records" stripe>
            <el-table-column prop="title" label="资料标题" min-width="210" />
            <el-table-column prop="knowledge_base" label="知识库" width="100" />
            <el-table-column prop="reason" label="删除原因" min-width="240" />
            <el-table-column prop="removed_document_count" label="移除分块" width="100" />
            <el-table-column prop="deleted_by" label="操作人" width="110" />
            <el-table-column label="删除时间" min-width="180">
              <template #default="{ row }">{{ formatTime(row.deleted_at) }}</template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </section>

    <section class="history-panel">
      <div class="panel-heading compact">
        <div>
          <h3>处理记录</h3>
          <p>批次保留在本地持久化审核仓库，服务重启后仍可继续处理。</p>
        </div>
      </div>
      <el-table :data="batches" stripe>
        <el-table-column prop="batch_id" label="批次编号" min-width="180" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="batchTagType(row.status)" effect="plain">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="人工通过 / 总拒绝" width="150">
          <template #default="{ row }">{{ row.approved_review_count ?? 0 }} / {{ (row.report.rejected_count || 0) + (row.manual_rejected_count || 0) }}</template>
        </el-table-column>
        <el-table-column label="质量" width="100">
          <template #default="{ row }">{{ percent(row.report.average_quality_score) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="activeBatch = row">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-drawer
      v-model="recordDrawerVisible"
      size="min(680px, 94vw)"
      :with-header="false"
      class="knowledge-detail-drawer"
    >
      <article v-if="selectedRecord" class="record-detail">
        <header class="record-detail-header">
          <div>
            <p class="eyebrow">知识资料审阅</p>
            <h2>{{ selectedRecord.title }}</h2>
          </div>
          <el-button :icon="Close" circle title="关闭详情" @click="recordDrawerVisible = false" />
        </header>

        <div class="record-status-line">
          <el-tag :type="recordTagType(selectedRecord.review_status)" effect="plain">
            {{ recordStatusLabel(selectedRecord.review_status) }}
          </el-tag>
          <span>质量评分 {{ percent(selectedRecord.quality_score) }}</span>
          <span>知识库 {{ selectedRecord.knowledge_base }}</span>
        </div>

        <el-alert
          v-if="selectedRecord.review_status === 'REJECTED'"
          :title="`人工拒绝：${selectedRecord.review_reason || '未填写原因'}`"
          :description="selectedRecord.review_note || undefined"
          type="error"
          :closable="false"
          show-icon
        />

        <dl class="record-metadata">
          <div>
            <dt>城市</dt>
            <dd>{{ selectedRecord.city }}</dd>
          </div>
          <div>
            <dt>资料类型</dt>
            <dd>{{ selectedRecord.category }}</dd>
          </div>
          <div>
            <dt>来源</dt>
            <dd>{{ selectedRecord.source }}</dd>
          </div>
          <div>
            <dt>来源等级</dt>
            <dd>{{ sourceTierLabel(selectedRecord.source_tier) }}</dd>
          </div>
          <div>
            <dt>正文来源</dt>
            <dd>{{ contentSourceLabel(selectedRecord.content_source) }}</dd>
          </div>
          <div>
            <dt>正文长度</dt>
            <dd>{{ selectedRecord.content.length }} 字</dd>
          </div>
          <div>
            <dt>更新时间</dt>
            <dd>{{ formatTime(selectedRecord.updated_at) }}</dd>
          </div>
          <div>
            <dt>记录编号</dt>
            <dd class="record-id">{{ selectedRecord.record_id }}</dd>
          </div>
          <div>
            <dt>审核人</dt>
            <dd>{{ selectedRecord.reviewed_by || '-' }}</dd>
          </div>
          <div>
            <dt>审核时间</dt>
            <dd>{{ formatTime(selectedRecord.reviewed_at) }}</dd>
          </div>
        </dl>

        <section v-if="selectedRecord.source_url" class="record-section">
          <h3>来源链接</h3>
          <a :href="selectedRecord.source_url" target="_blank" rel="noopener noreferrer">
            {{ selectedRecord.source_url }}
          </a>
        </section>

        <section class="record-section body-section">
          <div class="section-heading">
            <h3>正文内容</h3>
            <span>{{ selectedRecord.content.length }} 字</span>
          </div>
          <p class="record-body">{{ selectedRecord.content }}</p>
        </section>

        <section v-if="selectedRecord.tags?.length" class="record-section">
          <h3>资料标签</h3>
          <div class="record-tags">
            <el-tag v-for="tag in selectedRecord.tags" :key="tag" effect="plain">{{ tag }}</el-tag>
          </div>
        </section>
      </article>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, CircleClose, Close, DataAnalysis, Delete, Plus, Refresh, RefreshLeft, Search, UploadFilled, View } from '@element-plus/icons-vue'
import {
  collectKnowledge,
  deleteApprovedKnowledgeRecord,
  fetchKnowledgeBatches,
  fetchKnowledgeStats,
  previewKnowledge,
  publishKnowledge,
  rebuildKnowledgeIndex,
  rejectKnowledgeBatch,
  reopenKnowledgeBatch,
  reviewKnowledgeRecord
} from '../api/admin.js'

const categoryOptions = [
  { label: '景点攻略', value: '景点', base: 'poi' },
  { label: '美食资料', value: '美食', base: 'food' },
  { label: '酒店住宿', value: '酒店', base: 'hotel' },
  { label: '交通资料', value: '交通', base: 'transport' },
  { label: '门票信息', value: '门票', base: 'ticket' },
  { label: '综合攻略', value: '攻略', base: 'guide' }
]
const modeOptions = [
  { label: '手工资料', value: 'manual' },
  { label: '离线采集', value: 'collect' }
]

const stats = ref({})
const batches = ref([])
const activeBatch = ref(null)
const inputMode = ref('manual')
const reviewTab = ref('cleaned')
const loading = ref(false)
const previewing = ref(false)
const collecting = ref(false)
const publishing = ref(false)
const rebuilding = ref(false)
const rejectingBatch = ref(false)
const reopeningBatch = ref(false)
const reviewingRecordId = ref('')
const deletingRecordId = ref('')
const records = ref([])
const recordDrawerVisible = ref(false)
const selectedRecord = ref(null)
const draft = reactive(emptyDraft())
const collection = reactive({ destination: '成都', category: '景点', knowledge_base: 'poi', query: '成都适合亲子旅行的景点攻略' })
const eligibleReviewCount = computed(() => (
  activeBatch.value?.records?.filter(item => item.review_status !== 'REJECTED').length || 0
))

function emptyDraft() {
  return {
    city: '成都', category: '景点', knowledge_base: 'poi', source_tier: 'official',
    source: 'manual', title: '', source_url: '', content: '', tagsText: ''
  }
}

function resetDraft() {
  Object.assign(draft, emptyDraft())
}

function addRecord() {
  if (!draft.title.trim() || !draft.content.trim() || !draft.city.trim()) {
    ElMessage.warning('请至少填写城市、标题和正文')
    return
  }
  const option = categoryOptions.find(item => item.value === draft.category)
  records.value.push({
    ...draft,
    knowledge_base: option?.base || 'guide',
    tags: draft.tagsText.split(/[,，、]/).map(item => item.trim()).filter(Boolean),
    updated_at: new Date().toISOString()
  })
  resetDraft()
}

function fillDemo() {
  records.value = [
    {
      city: '成都市', category: '景区', knowledge_base: 'poi', source: '成都大熊猫繁育研究基地官网',
      source_tier: 'official', title: '成都大熊猫繁育研究基地参观提示',
      source_url: 'https://example.com/panda/guide?utm_source=demo',
      content: '熊猫基地适合上午参观，建议预留三到四小时。节假日客流较多，应提前核对预约要求和当日开放时间。',
      tags: ['亲子', '自然'], updated_at: new Date().toISOString()
    },
    {
      city: '成都', category: '景点', knowledge_base: 'poi', source: '社区转载', source_tier: 'community',
      title: '熊猫基地重复摘要', source_url: 'https://example.com/panda/guide',
      content: '这是同一链接的重复资料，用来演示 Pandas 根据规范化 URL 自动去重。', tags: ['亲子']
    },
    {
      city: '', category: '景点', knowledge_base: 'poi', source: '未知', source_tier: 'unknown',
      title: '不完整资料', source_url: '', content: '太短', tags: []
    },
    {
      city: '成都', category: '餐饮', knowledge_base: 'food', source: '编辑整理', source_tier: 'trusted',
      title: '成都火锅就餐建议', source_url: '',
      content: '成都火锅常见牛油锅底，热门时段建议错峰到店，并根据同行者的口味选择辣度和锅底。', tags: ['火锅', '本地美食']
    }
  ]
  ElMessage.success('已填入包含重复项和缺失项的演示数据')
}

async function runPreview() {
  previewing.value = true
  try {
    activeBatch.value = await previewKnowledge(records.value)
    reviewTab.value = 'cleaned'
    await loadOverview(false)
    ElMessage.success('清洗完成，请检查质量报告后发布')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    previewing.value = false
  }
}

function syncCollectionBase() {
  collection.knowledge_base = categoryOptions.find(item => item.value === collection.category)?.base || 'guide'
}

async function runCollection() {
  if (!collection.destination.trim() || !collection.query.trim()) {
    ElMessage.warning('请填写目的地和采集主题')
    return
  }
  collecting.value = true
  try {
    activeBatch.value = await collectKnowledge(collection)
    reviewTab.value = 'cleaned'
    await loadOverview(false)
    ElMessage.success('采集完成，已进入人工审核')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    collecting.value = false
  }
}

async function publishActiveBatch() {
  try {
    await ElMessageBox.confirm(
      `确认通过并发布 ${eligibleReviewCount.value} 条资料？人工拒绝的资料不会写入 Chroma。`,
      '发布知识批次',
      { type: 'warning', confirmButtonText: '确认发布', cancelButtonText: '继续审核' }
    )
  } catch {
    return
  }
  publishing.value = true
  try {
    activeBatch.value = await publishKnowledge(activeBatch.value.batch_id)
    await loadOverview(false)
    ElMessage.success(`已发布 ${activeBatch.value.published_document_count} 个向量文档`)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    publishing.value = false
  }
}

async function approveRecord(record) {
  await updateRecordReview(record, { status: 'APPROVED' }, '资料已通过人工审核')
}

async function rejectRecord(record) {
  let reason
  try {
    const result = await ElMessageBox.prompt(
      `请说明拒绝“${record.title}”的原因，便于后续追溯。`,
      '拒绝资料',
      {
        type: 'warning',
        confirmButtonText: '确认拒绝',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：来源过期、内容与标题不符',
        inputValidator: value => Boolean(value?.trim()) || '必须填写拒绝原因'
      }
    )
    reason = result.value.trim()
  } catch {
    return
  }
  await updateRecordReview(record, { status: 'REJECTED', reason }, '资料已拒绝，不会进入知识库')
}

async function restoreRecord(record) {
  await updateRecordReview(record, { status: 'PENDING' }, '资料已恢复为待审核')
}

async function deleteApprovedRecord(record) {
  const published = activeBatch.value.status === 'PUBLISHED'
  let reason
  try {
    const result = await ElMessageBox.prompt(
      published
        ? `“${record.title}”已进入检索库，删除后将同步移除它的全部向量分块。`
        : `“${record.title}”已通过审核，删除后只保留审计记录。`,
      '删除已通过资料',
      {
        type: 'warning',
        confirmButtonText: published ? '删除并撤出知识库' : '确认删除',
        cancelButtonText: '取消',
        inputPlaceholder: '填写删除原因，例如：来源失效、内容错误',
        inputValidator: value => Boolean(value?.trim()) || '必须填写删除原因'
      }
    )
    reason = result.value.trim()
  } catch {
    return
  }

  deletingRecordId.value = record.record_id
  try {
    activeBatch.value = await deleteApprovedKnowledgeRecord(
      activeBatch.value.batch_id,
      record.record_id,
      { reason }
    )
    if (selectedRecord.value?.record_id === record.record_id) {
      selectedRecord.value = null
      recordDrawerVisible.value = false
    }
    await loadOverview(false)
    ElMessage.success(published ? '资料及其向量分块已删除' : '已通过资料已删除')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    deletingRecordId.value = ''
  }
}

async function updateRecordReview(record, payload, successMessage) {
  reviewingRecordId.value = record.record_id
  try {
    activeBatch.value = await reviewKnowledgeRecord(
      activeBatch.value.batch_id,
      record.record_id,
      payload
    )
    if (selectedRecord.value?.record_id === record.record_id) {
      selectedRecord.value = activeBatch.value.records.find(item => item.record_id === record.record_id)
    }
    await loadOverview(false)
    ElMessage.success(successMessage)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    reviewingRecordId.value = ''
  }
}

async function rejectActiveBatch() {
  let reason
  try {
    const result = await ElMessageBox.prompt(
      '驳回后该批次不能发布，可以稍后恢复审核。',
      '驳回知识批次',
      {
        type: 'warning',
        confirmButtonText: '确认驳回',
        cancelButtonText: '取消',
        inputPlaceholder: '填写整批驳回原因',
        inputValidator: value => Boolean(value?.trim()) || '必须填写驳回原因'
      }
    )
    reason = result.value.trim()
  } catch {
    return
  }
  rejectingBatch.value = true
  try {
    activeBatch.value = await rejectKnowledgeBatch(activeBatch.value.batch_id, { reason })
    await loadOverview(false)
    ElMessage.success('批次已驳回')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    rejectingBatch.value = false
  }
}

async function reopenActiveBatch() {
  try {
    await ElMessageBox.confirm('确认将该批次恢复为待审核状态？', '恢复审核', {
      type: 'info',
      confirmButtonText: '恢复',
      cancelButtonText: '取消'
    })
  } catch {
    return
  }
  reopeningBatch.value = true
  try {
    activeBatch.value = await reopenKnowledgeBatch(activeBatch.value.batch_id)
    await loadOverview(false)
    ElMessage.success('批次已恢复审核')
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    reopeningBatch.value = false
  }
}

async function loadOverview(showLoading = true) {
  if (showLoading) loading.value = true
  try {
    const [nextStats, nextBatches] = await Promise.all([fetchKnowledgeStats(), fetchKnowledgeBatches()])
    stats.value = nextStats
    batches.value = nextBatches?.batches || []
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    loading.value = false
  }
}

async function rebuildIndex() {
  try {
    await ElMessageBox.confirm(
      '系统将清空现有向量分块，并仅使用已发布、已通过的审核记录重新建立索引。',
      '重建知识库索引',
      { type: 'warning', confirmButtonText: '确认重建', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  rebuilding.value = true
  try {
    const result = await rebuildKnowledgeIndex()
    await loadOverview(false)
    ElMessage.success(`重建完成：写入 ${result.rebuilt_document_count} 个向量分块`)
  } catch (error) {
    ElMessage.error(error.message)
  } finally {
    rebuilding.value = false
  }
}

function sourceTierLabel(value) {
  return ({ official: '官方来源', trusted: '可信编辑', commercial: '商业平台', community: '社区内容', unknown: '来源待核验' })[value] || value
}

function contentSourceLabel(value) {
  return ({ full_page: '完整网页抓取', search_summary: '搜索摘要降级', manual: '管理员录入' })[value] || '管理员录入'
}

function rejectionLabel(value) {
  return ({ TITLE_MISSING: '缺少标题', CONTENT_TOO_SHORT: '正文过短', CITY_MISSING: '缺少城市', CITY_CONTENT_MISMATCH: '城市标签与正文冲突', CATEGORY_UNSUPPORTED: '类型不支持', KNOWLEDGE_BASE_UNSUPPORTED: '知识库不支持', DUPLICATE_RECORD: '重复资料' })[value] || value
}

function statusLabel(value) {
  return ({ PUBLISHED: '已发布', REJECTED: '已驳回', PREVIEWED: '待审核' })[value] || value
}

function batchTagType(value) {
  return ({ PUBLISHED: 'success', REJECTED: 'danger', PREVIEWED: 'warning' })[value] || 'info'
}

function recordStatusLabel(value) {
  return ({ APPROVED: '已通过', REJECTED: '已拒绝', PENDING: '待审核' })[value] || '待审核'
}

function recordTagType(value) {
  return ({ APPROVED: 'success', REJECTED: 'danger', PENDING: 'warning' })[value] || 'warning'
}

function percent(value) {
  return `${Math.round((value || 0) * 100)}%`
}

function formatTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
}

function openRecordDetails(record) {
  selectedRecord.value = record
  recordDrawerVisible.value = true
}

onMounted(loadOverview)
</script>

<style scoped>
.knowledge-page {
  display: grid;
  gap: 20px;
}

.knowledge-summary,
.panel-heading,
.review-actions,
.form-actions,
.list-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.summary-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.knowledge-summary {
  padding: 4px 2px;
}

.summary-copy h2 {
  margin: 4px 0 6px;
  font-size: 24px;
}

.summary-copy p,
.panel-heading p,
.muted {
  color: var(--admin-text-muted);
  font-size: 13px;
}

.eyebrow {
  color: var(--admin-primary-dark) !important;
  font-size: 12px !important;
  font-weight: 800;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}

.metric-item {
  min-height: 112px;
  padding: 20px;
  border-right: 1px solid var(--admin-border);
}

.metric-item:last-child {
  border-right: 0;
}

.metric-item span,
.metric-item small {
  display: block;
  color: var(--admin-text-muted);
  font-size: 12px;
}

.metric-item strong {
  display: block;
  margin: 6px 0 3px;
  font-size: 28px;
}

.metric-item.pending strong { color: #b7791f; }
.metric-item.rejected strong { color: var(--el-color-danger); }
.metric-item.published strong { color: var(--admin-primary-dark); }

.workspace-panel,
.review-panel,
.history-panel {
  padding: 22px 24px;
  border: 1px solid var(--admin-border);
  border-radius: 8px;
  background: #fff;
}

.panel-heading {
  margin-bottom: 20px;
}

.panel-heading h3 {
  margin: 3px 0 5px;
  font-size: 17px;
}

.panel-heading.compact {
  margin-bottom: 14px;
}

.manual-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(280px, 0.7fr);
  gap: 24px;
}

.record-form {
  padding-right: 24px;
  border-right: 1px solid var(--admin-border);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.collection-grid .query-field {
  grid-column: span 2;
}

.form-actions {
  justify-content: flex-end;
  flex-wrap: wrap;
}

.record-items {
  display: grid;
  gap: 8px;
  margin-top: 12px;
  max-height: 450px;
  overflow: auto;
}

.record-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--admin-border);
  border-radius: 6px;
}

.record-item p {
  margin-top: 4px;
  color: var(--admin-text-muted);
  font-size: 12px;
}

.collector-form .el-alert {
  margin-bottom: 18px;
}

.quality-strip {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  margin-bottom: 16px;
  border: 1px solid var(--admin-border);
  border-radius: 6px;
}

.quality-strip div {
  padding: 14px 16px;
  border-right: 1px solid var(--admin-border);
}

.quality-strip div:last-child { border-right: 0; }
.quality-strip span { display: block; color: var(--admin-text-muted); font-size: 12px; }
.quality-strip strong { display: block; margin-top: 4px; font-size: 19px; }
.reason-tag { margin: 2px 6px 2px 0; }

.record-review-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}

.content-preview {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
}

.content-preview p {
  display: -webkit-box;
  min-width: 0;
  overflow: hidden;
  color: var(--admin-text-secondary);
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.content-preview .el-button {
  flex: 0 0 auto;
}

.record-detail {
  min-height: 100%;
  color: var(--admin-text);
}

.record-detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 4px 0 20px;
  border-bottom: 1px solid var(--admin-border);
}

.record-detail-header h2 {
  max-width: 24ch;
  margin-top: 5px;
  font-size: 22px;
  line-height: 1.45;
}

.record-status-line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 16px;
  padding: 16px 0;
  color: var(--admin-text-secondary);
  font-size: 13px;
  border-bottom: 1px solid var(--admin-border);
}

.record-metadata {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin: 0;
  border-bottom: 1px solid var(--admin-border);
}

.record-metadata > div {
  padding: 16px 0;
  border-bottom: 1px solid var(--admin-border);
}

.record-metadata > div:nth-child(odd) {
  padding-right: 20px;
}

.record-metadata > div:nth-child(even) {
  padding-left: 20px;
}

.record-metadata > div:nth-last-child(-n + 2) {
  border-bottom: 0;
}

.record-metadata dt {
  margin-bottom: 5px;
  color: var(--admin-text-muted);
  font-size: 12px;
}

.record-metadata dd {
  min-width: 0;
  margin: 0;
  font-size: 14px;
  font-weight: 650;
  overflow-wrap: anywhere;
}

.record-id {
  font-family: Consolas, "SFMono-Regular", monospace;
  font-size: 12px !important;
  font-weight: 500 !important;
}

.record-section {
  padding: 22px 0;
  border-bottom: 1px solid var(--admin-border);
}

.record-section:last-child {
  border-bottom: 0;
}

.record-section h3 {
  margin-bottom: 12px;
  font-size: 14px;
}

.record-section a {
  display: inline-block;
  max-width: 100%;
  color: var(--admin-primary-dark);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.section-heading span {
  color: var(--admin-text-muted);
  font-size: 12px;
}

.record-body {
  max-width: 70ch;
  color: var(--admin-text-secondary);
  font-size: 15px;
  line-height: 1.9;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.record-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

@media (max-width: 1100px) {
  .metric-grid { grid-template-columns: repeat(2, 1fr); }
  .metric-item:nth-child(2) { border-right: 0; }
  .metric-item:nth-child(-n+2) { border-bottom: 1px solid var(--admin-border); }
  .manual-workspace { grid-template-columns: 1fr; }
  .record-form { padding-right: 0; border-right: 0; }
  .form-grid { grid-template-columns: repeat(2, 1fr); }
  .quality-strip { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 640px) {
  .record-metadata { grid-template-columns: 1fr; }
  .record-metadata > div:nth-child(n) { padding: 14px 0; border-bottom: 1px solid var(--admin-border); }
  .record-metadata > div:last-child { border-bottom: 0; }
}
</style>
