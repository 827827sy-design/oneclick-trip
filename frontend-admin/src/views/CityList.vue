<template>
  <div>
    <div class="table-card">
      <div class="card-header">
        <div class="header-left">
          <h3>🏙️ 城市列表</h3>
          <el-input
            v-model="searchKeyword"
            placeholder="搜索城市名称"
            prefix-icon="Search"
            clearable
            class="admin-search"
            style="width:200px"
            @input="handleSearch"
          />
        </div>
        <div class="header-right">
          <el-button class="admin-btn-primary" @click="openDialog()">
            <el-icon><Plus /></el-icon> 新增城市
          </el-button>
        </div>
      </div>
      <div class="card-body">
        <el-table :data="list" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="城市名称" min-width="120" />
          <el-table-column prop="province" label="省份" width="100" />
          <el-table-column prop="summary" label="简介" min-width="220" show-overflow-tooltip />
          <el-table-column prop="bestSeason" label="最佳季节" width="100" />
          <el-table-column prop="sortOrder" label="排序" width="80" align="center" />
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
              <el-popconfirm title="确定删除该城市吗？关联数据也会受影响" @confirm="handleDelete(row.id)">
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
      :title="editingId ? '编辑城市' : '新增城市'"
      width="560px"
      @close="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="城市名称" prop="name">
              <el-input v-model="form.name" placeholder="例如：成都" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属省份" prop="province">
              <el-input v-model="form.province" placeholder="例如：四川" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="简介" prop="summary">
          <el-input v-model="form.summary" type="textarea" :rows="3" placeholder="城市简介描述" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="最佳季节" prop="bestSeason">
              <el-input v-model="form.bestSeason" placeholder="例如：春秋" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="排序号" prop="sortOrder">
              <el-input-number v-model="form.sortOrder" :min="0" :max="9999" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="图片URL" prop="imageUrl">
              <el-input v-model="form.imageUrl" placeholder="https://..." />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="状态" prop="status">
              <el-switch
                v-model="form.status"
                :active-value="1"
                :inactive-value="0"
                active-text="启用"
                inactive-text="禁用"
              />
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
import { fetchCities, fetchCity, createCity, updateCity, deleteCity } from '../api/admin.js'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const page = ref(1)
const size = ref(10)
const total = ref(0)
const searchKeyword = ref('')
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)

const form = reactive({
  name: '',
  province: '',
  summary: '',
  bestSeason: '',
  imageUrl: '',
  sortOrder: 0,
  status: 1
})

const rules = {
  name: [{ required: true, message: '请输入城市名称', trigger: 'blur' }],
  province: [{ required: true, message: '请输入省份', trigger: 'blur' }]
}

let searchTimer = null

onMounted(() => { loadData() })

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (searchKeyword.value) params.keyword = searchKeyword.value
    const data = await fetchCities(params)
    list.value = data.records || []
    total.value = data.total || 0
  } catch {
    ElMessage.error('加载城市列表失败')
  }
  loading.value = false
}

function handleSearch() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; loadData() }, 300)
}

async function openDialog(row) {
  if (row) {
    editingId.value = row.id
    try {
      const data = await fetchCity(row.id)
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
    name: '', province: '', summary: '', bestSeason: '',
    imageUrl: '', sortOrder: 0, status: 1
  })
  formRef.value?.resetFields()
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editingId.value) {
      await updateCity(editingId.value, form)
      ElMessage.success('城市已更新')
    } else {
      await createCity(form)
      ElMessage.success('城市已创建')
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
    await deleteCity(id)
    ElMessage.success('已删除')
    loadData()
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>
