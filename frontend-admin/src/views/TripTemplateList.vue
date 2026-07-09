<template>
  <div>
    <div class="table-card">
      <div class="card-header">
        <div class="header-left">
          <h3>⭐ 行程模板</h3>
          <el-select
            v-model="filterCityId"
            placeholder="按城市筛选"
            clearable
            style="width:160px"
            @change="loadData"
          >
            <el-option
              v-for="city in cityOptions"
              :key="city.id"
              :label="city.name"
              :value="city.id"
            />
          </el-select>
        </div>
        <div class="header-right">
          <el-button class="admin-btn-primary" @click="openDialog()">
            <el-icon><Plus /></el-icon> 新增模板
          </el-button>
        </div>
      </div>
      <div class="card-body">
        <el-table :data="list" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="title" label="模板标题" min-width="180" />
          <el-table-column label="所属城市" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ getCityName(row.cityId) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="days" label="天数" width="70" align="center" />
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
          <el-table-column prop="pace" label="节奏" width="90">
            <template #default="{ row }">
              {{ row.pace === 'RELAXED' ? '轻松' : row.pace === 'MODERATE' ? '适中' : '紧凑' }}
            </template>
          </el-table-column>
          <el-table-column prop="summary" label="简介" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.status === 1 ? 'success' : 'info'" size="small" effect="plain">
                {{ row.status === 1 ? '启用' : '禁用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="openDialog(row)">编辑</el-button>
              <el-popconfirm title="确定删除吗？" @confirm="handleDelete(row.id)">
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

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑模板' : '新增模板'"
      width="560px"
      @close="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-form-item label="模板标题" prop="title">
          <el-input v-model="form.title" placeholder="例如：成都3日经典游" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="所属城市" prop="cityId">
              <el-select v-model="form.cityId" placeholder="选择城市" style="width:100%">
                <el-option v-for="city in cityOptions" :key="city.id" :label="city.name" :value="city.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="天数" prop="days">
              <el-input-number v-model="form.days" :min="1" :max="30" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="预算等级" prop="budgetLevel">
              <el-select v-model="form.budgetLevel" style="width:100%">
                <el-option label="经济" value="LOW" />
                <el-option label="适中" value="MEDIUM" />
                <el-option label="舒适" value="HIGH" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="旅行节奏" prop="pace">
              <el-select v-model="form.pace" style="width:100%">
                <el-option label="轻松" value="RELAXED" />
                <el-option label="适中" value="MODERATE" />
                <el-option label="紧凑" value="INTENSE" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="简介" prop="summary">
          <el-input v-model="form.summary" type="textarea" :rows="3" placeholder="模板简介" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="封面URL">
              <el-input v-model="form.coverUrl" placeholder="https://..." />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态">
              <el-switch v-model="form.status" :active-value="1" :inactive-value="0" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button class="admin-btn-primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { fetchTemplates, fetchTemplate, createTemplate, updateTemplate, deleteTemplate, fetchCities } from '../api/admin.js'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const page = ref(1)
const size = ref(10)
const total = ref(0)
const filterCityId = ref(null)
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const cityOptions = ref([])

const form = reactive({
  title: '', cityId: null, days: 3, budgetLevel: 'MEDIUM',
  pace: 'RELAXED', summary: '', coverUrl: '', status: 1
})

const rules = {
  title: [{ required: true, message: '请输入模板标题', trigger: 'blur' }],
  cityId: [{ required: true, message: '请选择城市', trigger: 'change' }],
  days: [{ required: true, message: '请输入天数', trigger: 'blur' }]
}

onMounted(async () => {
  loadCities()
  loadData()
})

async function loadCities() {
  try {
    const data = await fetchCities({ size: 200 })
    cityOptions.value = data.records || []
  } catch { /* ignore */ }
}

function getCityName(cityId) {
  const city = cityOptions.value.find(c => c.id === cityId)
  return city?.name || '-'
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (filterCityId.value) params.cityId = filterCityId.value
    const data = await fetchTemplates(params)
    list.value = data.records || []
    total.value = data.total || 0
  } catch {
    ElMessage.error('加载模板列表失败')
  }
  loading.value = false
}

async function openDialog(row) {
  if (row) {
    editingId.value = row.id
    try {
      const data = await fetchTemplate(row.id)
      Object.assign(form, data)
    } catch {
      Object.assign(form, row)
    }
  } else {
    editingId.value = null
  }
  dialogVisible.value = true
}

function resetForm() {
  editingId.value = null
  Object.assign(form, {
    title: '', cityId: null, days: 3, budgetLevel: 'MEDIUM',
    pace: 'RELAXED', summary: '', coverUrl: '', status: 1
  })
  formRef.value?.resetFields()
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editingId.value) {
      await updateTemplate(editingId.value, form)
      ElMessage.success('模板已更新')
    } else {
      await createTemplate(form)
      ElMessage.success('模板已创建')
    }
    dialogVisible.value = false
    resetForm()
    loadData()
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  }
  saving.value = false
}

async function handleDelete(id) {
  try {
    await deleteTemplate(id)
    ElMessage.success('已删除')
    loadData()
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>
