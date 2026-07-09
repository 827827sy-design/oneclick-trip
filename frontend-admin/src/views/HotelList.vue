<template>
  <div>
    <div class="table-card">
      <div class="card-header">
        <div class="header-left">
          <h3>🏨 酒店列表</h3>
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
          <el-input
            v-model="searchKeyword"
            placeholder="搜索酒店"
            prefix-icon="Search"
            clearable
            class="admin-search"
            style="width:200px"
            @input="handleSearch"
          />
        </div>
        <div class="header-right">
          <el-button class="admin-btn-primary" @click="openDialog()">
            <el-icon><Plus /></el-icon> 新增酒店
          </el-button>
        </div>
      </div>
      <div class="card-body">
        <el-table :data="list" stripe style="width:100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="70" />
          <el-table-column prop="name" label="酒店名称" min-width="150" />
          <el-table-column label="所属城市" width="100">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ getCityName(row.cityId) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="area" label="区域" width="110" />
          <el-table-column label="价格等级" width="100">
            <template #default="{ row }">
              <el-tag
                :type="row.priceLevel === 'HIGH' ? 'danger' : row.priceLevel === 'MEDIUM' ? 'warning' : 'success'"
                size="small"
                effect="plain"
              >
                {{ row.priceLevel === 'HIGH' ? '高档' : row.priceLevel === 'MEDIUM' ? '中档' : '经济' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="均价" width="90">
            <template #default="{ row }">¥{{ row.avgPrice }}</template>
          </el-table-column>
          <el-table-column prop="rating" label="评分" width="80" align="center" />
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
      :title="editingId ? '编辑酒店' : '新增酒店'"
      width="560px"
      @close="resetForm"
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="酒店名称" prop="name">
              <el-input v-model="form.name" placeholder="例如：成都锦江宾馆" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属城市" prop="cityId">
              <el-select v-model="form.cityId" placeholder="选择城市" style="width:100%">
                <el-option v-for="city in cityOptions" :key="city.id" :label="city.name" :value="city.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="区域" prop="area">
              <el-input v-model="form.area" placeholder="例如：市中心、火车站" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="价格等级" prop="priceLevel">
              <el-select v-model="form.priceLevel" style="width:100%">
                <el-option label="经济" value="LOW" />
                <el-option label="中档" value="MEDIUM" />
                <el-option label="高档" value="HIGH" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="简介" prop="summary">
          <el-input v-model="form.summary" type="textarea" :rows="2" placeholder="酒店简介" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="均价">
              <el-input-number v-model="form.avgPrice" :min="0" :precision="2" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="评分">
              <el-input-number v-model="form.rating" :min="0" :max="5" :precision="1" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
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
import { fetchHotels, fetchHotel, createHotel, updateHotel, deleteHotel, fetchCities } from '../api/admin.js'
import { ElMessage } from 'element-plus'

const loading = ref(false)
const saving = ref(false)
const list = ref([])
const page = ref(1)
const size = ref(10)
const total = ref(0)
const searchKeyword = ref('')
const filterCityId = ref(null)
const dialogVisible = ref(false)
const editingId = ref(null)
const formRef = ref(null)
const cityOptions = ref([])

const form = reactive({
  name: '', cityId: null, area: '', summary: '',
  priceLevel: 'MEDIUM', avgPrice: 0, rating: 4.0, status: 1
})

const rules = {
  name: [{ required: true, message: '请输入酒店名称', trigger: 'blur' }],
  cityId: [{ required: true, message: '请选择城市', trigger: 'change' }],
  area: [{ required: true, message: '请输入区域', trigger: 'blur' }],
  priceLevel: [{ required: true, message: '请选择价格等级', trigger: 'change' }]
}

let searchTimer = null

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
    if (searchKeyword.value) params.keyword = searchKeyword.value
    if (filterCityId.value) params.cityId = filterCityId.value
    const data = await fetchHotels(params)
    list.value = data.records || []
    total.value = data.total || 0
  } catch {
    ElMessage.error('加载酒店列表失败')
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
      const data = await fetchHotel(row.id)
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
    name: '', cityId: null, area: '', summary: '',
    priceLevel: 'MEDIUM', avgPrice: 0, rating: 4.0, status: 1
  })
  formRef.value?.resetFields()
}

async function handleSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (editingId.value) {
      await updateHotel(editingId.value, form)
      ElMessage.success('酒店已更新')
    } else {
      await createHotel(form)
      ElMessage.success('酒店已创建')
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
    await deleteHotel(id)
    ElMessage.success('已删除')
    loadData()
  } catch {
    ElMessage.error('删除失败')
  }
}
</script>
