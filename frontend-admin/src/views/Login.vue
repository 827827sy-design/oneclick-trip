<template>
  <div class="login-page-wrapper">
    <div class="login-container">
      <div class="login-left">
        <div class="login-branding">
          <span class="brand-emoji">🧭</span>
          <div>
            <h1>一键游</h1>
            <p>管理系统</p>
          </div>
        </div>
        <div class="login-description">
          <p>管理城市、景点、美食、酒店、行程模板和用户数据。</p>
          <div class="feature-list">
            <span>📊 数据仪表盘</span>
            <span>👥 用户管理</span>
            <span>🏙️ 内容管理</span>
            <span>📋 订单管理</span>
          </div>
        </div>
      </div>

      <div class="login-right">
        <div class="login-card">
          <h2>管理员登录</h2>
          <el-form
            ref="formRef"
            :model="loginForm"
            :rules="rules"
            label-position="top"
            @submit.prevent="handleLogin"
          >
            <el-form-item label="账号" prop="username">
              <el-input
                v-model="loginForm.username"
                placeholder="请输入管理员账号"
                :prefix-icon="User"
                size="large"
              />
            </el-form-item>
            <el-form-item label="密码" prop="password">
              <el-input
                v-model="loginForm.password"
                type="password"
                placeholder="请输入密码"
                :prefix-icon="Lock"
                size="large"
                show-password
                @keydown.enter="handleLogin"
              />
            </el-form-item>
            <el-alert
              v-if="loginError"
              :title="loginError"
              type="error"
              show-icon
              :closable="false"
              style="margin-bottom:16px"
            />
            <el-button
              class="admin-btn-primary"
              style="width:100%;height:46px;font-size:16px"
              :loading="loading"
              @click="handleLogin"
            >
              {{ loading ? '登录中...' : '登录管理系统' }}
            </el-button>
          </el-form>
          <div class="login-hint">
            仅限管理员账号登录
          </div>
        </div>
      </div>
    </div>

    <div class="login-bg-shapes">
      <div class="shape shape-1"></div>
      <div class="shape shape-2"></div>
      <div class="shape shape-3"></div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { adminLogin } from '../api/admin.js'

const router = useRouter()
const loading = ref(false)
const loginError = ref('')
const formRef = ref(null)

const loginForm = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function handleLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loginError.value = ''
  loading.value = true
  try {
    const data = await adminLogin({
      username: loginForm.username,
      password: loginForm.password
    })
    if (data.role !== 'ADMIN') {
      loginError.value = '该账号不是管理员，无法登录管理系统'
      return
    }
    localStorage.setItem('oneclick_trip_token', data.token)
    localStorage.setItem('oneclick_trip_user', JSON.stringify(data))
    router.push('/dashboard')
  } catch (error) {
    loginError.value = error.message || '登录失败，请检查账号和密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page-wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 15% 30%, rgba(18, 184, 166, 0.15), transparent 35%),
    radial-gradient(circle at 80% 70%, rgba(255, 107, 53, 0.08), transparent 30%),
    linear-gradient(135deg, #f4faf8 0%, #e7f0f5 50%, #f5f9f8 100%);
  position: relative;
  overflow: hidden;
}

.login-bg-shapes {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.shape {
  position: absolute;
  border-radius: 50%;
  opacity: 0.06;
}

.shape-1 {
  width: 500px;
  height: 500px;
  background: var(--admin-primary);
  top: -150px;
  right: -100px;
}

.shape-2 {
  width: 350px;
  height: 350px;
  background: var(--admin-orange);
  bottom: -100px;
  left: -80px;
}

.shape-3 {
  width: 200px;
  height: 200px;
  background: var(--admin-primary);
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.login-container {
  display: flex;
  max-width: 880px;
  width: 90%;
  background: white;
  border-radius: 24px;
  overflow: hidden;
  box-shadow: 0 24px 72px rgba(20, 66, 62, 0.18);
  position: relative;
  z-index: 1;
}

.login-left {
  flex: 1;
  background: linear-gradient(135deg, #0a5c54 0%, #0e9f90 50%, #12b8a6 100%);
  color: white;
  padding: 48px 40px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.login-branding {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-emoji {
  width: 54px;
  height: 54px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
}

.login-branding h1 {
  font-size: 28px;
  font-weight: 800;
  margin: 0;
  line-height: 1.1;
}

.login-branding p {
  margin: 4px 0 0;
  font-size: 15px;
  opacity: 0.8;
}

.login-description p {
  margin: 0 0 20px;
  font-size: 15px;
  line-height: 1.7;
  opacity: 0.85;
  max-width: 280px;
}

.feature-list {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.feature-list span {
  background: rgba(255, 255, 255, 0.15);
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
}

.login-right {
  flex: 1;
  padding: 48px 40px;
  display: flex;
  align-items: center;
}

.login-card {
  width: 100%;
}

.login-card h2 {
  margin: 0 0 28px;
  font-size: 22px;
  font-weight: 800;
  color: var(--admin-text);
}

.login-hint {
  text-align: center;
  margin-top: 20px;
  color: var(--admin-text-muted);
  font-size: 12px;
}

@media (max-width: 768px) {
  .login-container {
    flex-direction: column;
    border-radius: 16px;
  }
  .login-left {
    padding: 32px 24px;
  }
  .login-right {
    padding: 32px 24px;
  }
}
</style>
