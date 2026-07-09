<template>
  <div class="prototype-stage">
    <aside class="project-panel">
      <div class="project-brand">
        <span>🧭</span>
        <div>
          <strong>一键游</strong>
          <small>Vue 3 + Spring Boot MVP</small>
        </div>
      </div>
      <p>
        当前界面沿用之前的小程序原型。AI 助手先保留入口，真实能力后续接入 FastAPI。
      </p>
      <div class="status-card">
        <span>后端状态</span>
        <strong :class="{ ok: backendOnline }">{{ backendOnline ? '已连接' : '使用本地演示数据' }}</strong>
      </div>
      <div class="status-card">
        <span>生成方式</span>
        <strong>规则版</strong>
      </div>
      <div class="status-card">
        <span>登录状态</span>
        <strong :class="{ ok: isAuthenticated }">{{ isAuthenticated ? currentUser?.nickname || '已登录' : '等待登录' }}</strong>
      </div>
    </aside>

    <main class="phone-frame">
      <div class="status-bar">
        <span class="time">9:41</span>
        <span class="status-icons">5G ▮▮▮▮ 🔋 85%</span>
      </div>

      <section class="page login-page" :class="{ active: activePage === 'login' }">
        <div class="login-hero">
          <div class="login-brand">
            <span>🧭</span>
            <div>
              <strong>一键游</strong>
              <small>登录后继续生成你的旅行攻略</small>
            </div>
          </div>
          <div class="login-copy">
            <span>国内游 · 智能行程</span>
            <h1>把想去的地方，变成能出发的路线</h1>
            <p>保存偏好、行程和城市资料，后续 AI 助手会基于你的旅行方式继续优化方案。</p>
          </div>
        </div>

        <form class="login-form" @submit.prevent="handleLogin">
          <label>
            <span>账号</span>
            <input v-model.trim="loginForm.username" autocomplete="username" placeholder="admin 或 user" />
          </label>
          <label>
            <span>密码</span>
            <input v-model="loginForm.password" autocomplete="current-password" placeholder="请输入密码" type="password" />
          </label>
          <p v-if="loginError" class="login-error">{{ loginError }}</p>
          <button class="login-button" type="submit" :disabled="loginLoading">
            {{ loginLoading ? '登录中...' : '登录并开始规划' }}
          </button>
          <div class="demo-account">
            <span>体验账号</span>
            <button type="button" @click="fillDemoAccount('admin')">admin / 123456</button>
            <button type="button" @click="fillDemoAccount('user')">user / 123456</button>
          </div>
        </form>
      </section>

      <section class="page" :class="{ active: activePage === 'home' }">
        <div class="nav-bar nav-split">
          <span class="brand-title">🧭 一键游</span>
          <span class="nav-muted">{{ currentUser?.nickname || 'AI 旅行管家' }}</span>
        </div>

        <div class="ai-hero">
          <div class="pill">国内游 · 懒人攻略生成</div>
          <h1>说一句想去哪，剩下交给 AI</h1>
          <p>先问清你的旅行偏好，再查景点、路线、预算，生成能直接出门用的攻略。</p>
          <button class="hero-input" type="button" @click="go('planner')">
            <span>例如：从南京去成都玩 3 天，轻松一点，喜欢美食</span>
            <b>开始规划</b>
          </button>
        </div>

        <div class="home-steps">
          <div class="home-step"><strong>1</strong><span>问偏好<br />少填表</span></div>
          <div class="home-step"><strong>2</strong><span>查资料<br />看路线</span></div>
          <div class="home-step"><strong>3</strong><span>出方案<br />可修改</span></div>
        </div>

        <div class="home-actions">
          <button class="quick-item" type="button" @click="go('planner')">
            <span class="quick-icon blue">🗺️</span>
            <span>补全信息</span>
          </button>
          <button class="quick-item" type="button" @click="go('chat')">
            <span class="quick-icon green">💬</span>
            <span>继续问 AI</span>
          </button>
          <button class="quick-item" type="button" @click="goGuide('dest', selectedCityKey)">
            <span class="quick-icon yellow">🏔️</span>
            <span>景点攻略</span>
          </button>
          <button class="quick-item" type="button" @click="goGuide('food', selectedCityKey)">
            <span class="quick-icon orange">🍜</span>
            <span>美食</span>
          </button>
        </div>

        <div class="section-title">🔥 热门目的地</div>
        <div class="dest-scroll">
          <button
            v-for="(city, index) in displayCities"
            :key="city.id"
            class="dest-card"
            type="button"
            @click="goGuide('dest', city.key)"
          >
            <span v-if="index === 0" class="tag">热门 TOP1</span>
            <span class="bg" :style="{ background: destinationBackground(city, index) }">
              <b>{{ city.name }}</b>
              <small>{{ city.summaryShort }}</small>
            </span>
          </button>
        </div>

        <div class="section-title">⭐ 精选行程模板</div>
        <button class="trip-card" type="button" @click="go('trip')">
          <span class="cover" :style="{ background: chengduCover }">
            <b>成都3日经典游</b>
          </span>
          <span class="info">
            <strong>🐼 熊猫 + 火锅 + 古蜀文化</strong>
            <small>📍 成都 · 📅 3天2晚 · 💰 约3000元</small>
          </span>
        </button>
        <button class="trip-card" type="button" @click="toastText = '大理模板下一阶段开放'">
          <span class="cover gradient-blue">
            <b>大理丽江5日慢生活</b>
          </span>
          <span class="info">
            <strong>🏔️ 苍山洱海 + 丽江古城 + 玉龙雪山</strong>
            <small>📍 云南 · 📅 5天4晚 · 💰 约5000元</small>
          </span>
        </button>
      </section>

      <section class="page" :class="{ active: activePage === 'chat' }">
        <div class="nav-bar">
          <button class="back" type="button" @click="go('home')">‹</button>
          <span>AI 旅游助手</span>
          <button class="action" type="button" @click="go('planner')">规划</button>
        </div>
        <div class="chat-shell">
          <div class="msg ai">
            <span class="avatar">🤖</span>
            <div class="bubble">
              AI 助手先空出来。当前版本先完成城市资料、景点、美食、酒店和规则版行程生成。
            </div>
          </div>
          <div v-if="aiReply" class="msg ai">
            <span class="avatar">🧭</span>
            <div class="bubble">{{ aiReply }}</div>
          </div>
        </div>
        <div class="quick-btns">
          <button type="button" @click="callAiPlaceholder('我想从南京去成都玩 3 天')">测试占位接口</button>
          <button type="button" @click="go('planner')">去生成行程</button>
        </div>
        <div class="chat-input">
          <input v-model="aiInput" placeholder="AI 暂未接入，先保留输入框" @keydown.enter="callAiPlaceholder(aiInput)" />
          <button type="button" @click="callAiPlaceholder(aiInput)">↑</button>
        </div>
      </section>

      <section class="page" :class="{ active: activePage === 'planner' }">
        <div class="nav-bar">
          <button class="back" type="button" @click="go('home')">‹</button>
          <span>一键生成攻略</span>
        </div>
        <div class="planner-form">
          <div class="form-card">
            <h3>📍 基础信息</h3>
            <label>出发城市</label>
            <input v-model="planForm.departureCity" class="form-input" />
            <div class="form-row">
              <div>
                <label>目的地</label>
                <select v-model="planForm.cityId" class="form-input" @change="selectCityById(planForm.cityId)">
                  <option v-for="city in displayCities" :key="city.id" :value="city.id">{{ city.name }}</option>
                </select>
              </div>
              <div>
                <label>出行天数</label>
                <select v-model.number="planForm.days" class="form-input">
                  <option :value="2">2天</option>
                  <option :value="3">3天</option>
                  <option :value="4">4天</option>
                  <option :value="5">5天</option>
                </select>
              </div>
            </div>
            <div class="form-row">
              <div>
                <label>预算</label>
                <select v-model="planForm.budgetLevel" class="form-input">
                  <option value="LOW">经济</option>
                  <option value="MEDIUM">适中</option>
                  <option value="HIGH">舒适</option>
                </select>
              </div>
              <div>
                <label>人数</label>
                <select v-model.number="planForm.peopleCount" class="form-input">
                  <option :value="1">1人</option>
                  <option :value="2">2人</option>
                  <option :value="3">3人</option>
                  <option :value="4">4人</option>
                </select>
              </div>
            </div>
          </div>

          <div class="form-card">
            <h3>🎯 旅行偏好</h3>
            <div class="tag-group">
              <button
                v-for="tag in preferenceTags"
                :key="tag"
                class="tag-chip"
                :class="{ selected: planForm.interests.includes(tag) }"
                type="button"
                @click="togglePreference(tag)"
              >
                {{ tag }}
              </button>
            </div>
          </div>

          <button class="btn-block" type="button" :disabled="generateLoading" @click="generatePlan">
            {{ generateLoading ? '生成中...' : '✨ 生成规则版行程' }}
          </button>
        </div>
      </section>

      <section class="page" :class="{ active: activePage === 'trip' }">
        <div class="nav-bar">
          <button class="back" type="button" @click="go('home')">‹</button>
          <span>行程详情</span>
          <button class="action" type="button">保存</button>
        </div>
        <div class="trip-header">
          <h2>{{ plan?.title || '成都3日经典游' }}</h2>
          <div class="meta-row">
            <span>{{ plan?.days || 3 }} 天</span>
            <span>{{ plan?.peopleCount || 2 }} 人</span>
            <span>预算约 {{ plan?.totalBudget || 3000 }} 元</span>
          </div>
        </div>
        <div class="timeline">
          <div v-if="!plan" class="empty-plan">
            还没有生成真实行程，先展示原型里的成都经典游。
            <button type="button" @click="go('planner')">去生成</button>
          </div>
          <div v-for="day in planDays" :key="day.id || day.dayNo" class="day-block">
            <div class="day-header">{{ day.title }}</div>
            <div class="day-body">
              <div v-for="item in day.items" :key="item.id || item.title" class="timeline-item">
                <span class="timeline-dot" :class="item.itemType?.toLowerCase()"></span>
                <div>
                  <b>{{ item.startTime }} {{ item.title }}</b>
                  <p>{{ item.description }}</p>
                  <small>{{ item.address || '根据当天路线安排' }} · 约 {{ item.cost }} 元</small>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="page" :class="{ active: activePage === 'dest' }">
        <div class="nav-bar">
          <button class="back" type="button" @click="go('home')">‹</button>
          <span>景点攻略</span>
          <button class="action" type="button" @click="goGuide('food', selectedCityKey)">美食</button>
        </div>
        <CitySwitch :cities="displayCities" :active-key="selectedCityKey" @select="goGuide('dest', $event)" />
        <div class="dest-hero" :style="{ background: selectedGuide.hero }">
          <h2>{{ selectedGuide.destTitle }}</h2>
          <p>{{ selectedGuide.destSub }}</p>
        </div>
        <div class="dest-stats">
          <div><strong>{{ spots.length || selectedGuide.spots.length }}</strong><span>收录景点</span></div>
          <div><strong>{{ selectedGuide.routeCount }}</strong><span>推荐路线</span></div>
          <div><strong>{{ selectedGuide.avgTime }}</strong><span>适合天数</span></div>
        </div>
        <div class="section-title">🏔️ 必去景点</div>
        <div class="dest-scroll">
          <article v-for="spot in spotCards" :key="spot.name" class="guide-card">
            <div class="cover" :style="{ background: spot.cover }">{{ spot.name }}</div>
            <div class="guide-info">
              <h4>{{ spot.name }}</h4>
              <small>{{ spot.meta }}</small>
            </div>
          </article>
        </div>
        <div class="food-summary">
          <h3>{{ selectedGuide.routeTitle }}</h3>
          <p>{{ selectedGuide.routeDesc }}</p>
        </div>
      </section>

      <section class="page" :class="{ active: activePage === 'food' }">
        <div class="nav-bar">
          <button class="back" type="button" @click="go('home')">‹</button>
          <span>美食</span>
          <button class="action" type="button" @click="goGuide('dest', selectedCityKey)">景点</button>
        </div>
        <CitySwitch :cities="displayCities" :active-key="selectedCityKey" @select="goGuide('food', $event)" />
        <div class="food-summary">
          <h3>{{ selectedGuide.foodTitle }}</h3>
          <p>{{ selectedGuide.foodSub }}</p>
        </div>
        <div class="food-rail">
          <article v-for="food in foodCards" :key="food.name" class="food-card">
            <div class="food-photo" :style="{ background: food.cover }">
              <span>{{ food.tag }}</span>
              <b>{{ food.name }}</b>
            </div>
            <div class="food-info">
              <p>{{ food.summary }}</p>
              <div><span>{{ food.price }}</span><span>{{ food.time }}</span></div>
            </div>
          </article>
        </div>
        <button class="btn-block orange" type="button" @click="go('planner')">🍽️ 把美食加入行程</button>
      </section>

      <section class="page" :class="{ active: activePage === 'mine' }">
        <div class="nav-bar">我的</div>
        <div class="profile-header">
          <span class="profile-avatar" :class="currentAvatar.className">{{ currentAvatar.icon }}</span>
          <div>
            <h2>{{ currentUser?.nickname || '旅行者' }}</h2>
            <p>{{ currentUser?.username || '当前阶段：非 AI MVP 联调' }}</p>
          </div>
          <button class="profile-edit" type="button" @click="openProfileEdit">编辑</button>
        </div>
        <div class="menu-group">
          <button type="button" @click="openProfileEdit">个人资料 <span>›</span></button>
          <button type="button" @click="go('trip')">🗺️ 我的行程 <span>›</span></button>
          <button type="button" @click="toastText = '旅行偏好已在规划页保留，后续会同步到账户资料'">🎯 旅行偏好 <span>›</span></button>
          <button type="button" @click="go('dest')">🏔️ 景点攻略 <span>›</span></button>
          <button type="button" @click="go('food')">🍜 美食灵感 <span>›</span></button>
          <button type="button" @click="go('chat')">🤖 AI 助手 <span>›</span></button>
          <button type="button" @click="logout">退出登录 <span>›</span></button>
        </div>
      </section>

      <section class="page" :class="{ active: activePage === 'profileEdit' }">
        <div class="nav-bar">
          <button class="back" type="button" @click="go('mine')">‹</button>
          <span>编辑资料</span>
        </div>
        <form class="profile-form" @submit.prevent="handleProfileUpdate">
          <div class="profile-preview">
            <span class="profile-avatar large" :class="selectedProfileAvatar.className">{{ selectedProfileAvatar.icon }}</span>
            <div>
              <strong>{{ profileForm.nickname || '旅行者' }}</strong>
              <small>{{ currentUser?.username }}</small>
            </div>
          </div>

          <div class="form-card">
            <h3>选择头像</h3>
            <div class="avatar-grid">
              <button
                v-for="avatar in avatarOptions"
                :key="avatar.id"
                class="avatar-option"
                :class="{ selected: profileForm.avatarUrl === avatar.id }"
                type="button"
                @click="profileForm.avatarUrl = avatar.id"
              >
                <span class="profile-avatar small" :class="avatar.className">{{ avatar.icon }}</span>
                <small>{{ avatar.label }}</small>
              </button>
            </div>
          </div>

          <div class="form-card">
            <h3>基础资料</h3>
            <label>昵称</label>
            <input v-model.trim="profileForm.nickname" class="form-input" maxlength="64" placeholder="输入你的昵称" />
            <label>账号</label>
            <input class="form-input readonly" :value="currentUser?.username" readonly />
            <label>身份</label>
            <input class="form-input readonly" :value="currentUser?.role === 'ADMIN' ? '管理员' : '旅行者'" readonly />
          </div>

          <p v-if="profileError" class="login-error">{{ profileError }}</p>
          <button class="btn-block" type="submit" :disabled="profileLoading">
            {{ profileLoading ? '保存中...' : '保存资料' }}
          </button>
        </form>
      </section>

      <nav v-if="isAuthenticated" class="tabbar">
        <button :class="{ active: activePage === 'home' }" type="button" @click="go('home')">🏠<span>首页</span></button>
        <button :class="{ active: activePage === 'chat' }" type="button" @click="go('chat')">💬<span>AI助手</span></button>
        <button :class="{ active: activePage === 'planner' || activePage === 'trip' }" type="button" @click="go('planner')">🗺️<span>行程规划</span></button>
        <button :class="{ active: activePage === 'mine' || activePage === 'profileEdit' }" type="button" @click="go('mine')">👤<span>我的</span></button>
      </nav>

      <div v-if="toastText" class="toast" @animationend="toastText = ''">{{ toastText }}</div>
    </main>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { api, getToken, setToken } from './api/client'

const USER_KEY = 'oneclick_trip_user'

const CitySwitch = defineComponent({
  props: {
    cities: { type: Array, required: true },
    activeKey: { type: String, required: true }
  },
  emits: ['select'],
  setup(props, { emit }) {
    return () =>
      h(
        'div',
        { class: 'city-switch' },
        props.cities.map((city) =>
          h(
            'button',
            {
              type: 'button',
              class: { active: city.key === props.activeKey },
              onClick: () => emit('select', city.key)
            },
            city.name
          )
        )
      )
  }
})

const backendOnline = ref(false)
const currentUser = ref(readSavedUser())
const isAuthenticated = ref(Boolean(getToken()))
const activePage = ref(isAuthenticated.value ? 'home' : 'login')
const selectedCityKey = ref('chengdu')
const cities = ref([])
const spots = ref([])
const foods = ref([])
const hotels = ref([])
const plan = ref(null)
const generateLoading = ref(false)
const aiInput = ref('')
const aiReply = ref('')
const toastText = ref('')
const loginLoading = ref(false)
const loginError = ref('')
const profileLoading = ref(false)
const profileError = ref('')

const loginForm = reactive({
  username: 'admin',
  password: '123456'
})

const profileForm = reactive({
  nickname: currentUser.value?.nickname || '',
  avatarUrl: currentUser.value?.avatarUrl || 'avatar-compass'
})

const planForm = reactive({
  departureCity: '南京',
  cityId: 1,
  days: 3,
  peopleCount: 2,
  budgetLevel: 'MEDIUM',
  pace: 'RELAXED',
  interests: ['美食', '轻松']
})

const preferenceTags = ['美食', '轻松', '人文', '拍照', '亲子', '自然']

const avatarOptions = [
  { id: 'avatar-compass', icon: '🧭', label: '指南针', className: 'avatar-teal' },
  { id: 'avatar-backpack', icon: '🎒', label: '背包客', className: 'avatar-green' },
  { id: 'avatar-camera', icon: '📷', label: '摄影', className: 'avatar-blue' },
  { id: 'avatar-panda', icon: '🐼', label: '熊猫', className: 'avatar-warm' },
  { id: 'avatar-mountain', icon: '⛰️', label: '山野', className: 'avatar-lime' },
  { id: 'avatar-noodle', icon: '🍜', label: '美食', className: 'avatar-orange' }
]

const fallbackCities = [
  { id: 1, key: 'chengdu', name: '成都', province: '四川', summary: '适合轻松美食游，熊猫、古街、火锅和川西文化都很集中。', summaryShort: '天府之国 · 美食之都' },
  { id: 2, key: 'hangzhou', name: '杭州', province: '浙江', summary: '西湖、灵隐寺和龙井村适合慢节奏城市自然游。', summaryShort: '人间天堂 · 西湖美景' },
  { id: 3, key: 'xian', name: '西安', province: '陕西', summary: '古都文化和碳水美食密度高，适合历史路线。', summaryShort: '十三朝古都 · 碳水天堂' },
  { id: 4, key: 'dali', name: '大理', province: '云南', summary: '苍山洱海和古城生活感强，适合放松度假。', summaryShort: '苍山洱海 · 风花雪月' }
]

const guideData = {
  chengdu: {
    hero: 'linear-gradient(135deg, #ff7467, #ffb36f)',
    destTitle: '🐼 成都景点攻略',
    destSub: '天府之国 · 熊猫基地 · 市井古街 · 都江堰青城山',
    routeCount: 6,
    avgTime: '3天',
    routeTitle: '推荐玩法：市区经典 + 熊猫 + 都江堰',
    routeDesc: '第一天走市区古街和人文景点，第二天看熊猫和吃火锅，第三天安排都江堰青城山。',
    foodTitle: '🍜 成都美食灵感',
    foodSub: '午餐吃小吃，晚餐留给火锅或串串，避免一天全是重口味。',
    spots: [
      ['大熊猫基地', '🎫55元 · 3-4小时 · 建议早去', 'linear-gradient(135deg,#4facfe,#00f2fe)'],
      ['宽窄巷子', '免费 · 2-3小时 · 市井街区', 'linear-gradient(135deg,#a8edea,#fed6e3)'],
      ['杜甫草堂', '🎫60元 · 2-3小时 · 人文历史', 'linear-gradient(135deg,#f5f7fa,#c3cfe2)']
    ],
    foods: [
      ['火锅与串串', '晚餐首选', '适合安排在市区夜晚，人均 80-120 元。', '辣度可选', '约 1.5 小时', '/oneclick-trip-assets/chengdu-food-hotpot.png'],
      ['担担面与冰粉', '小吃集合', '适合午餐或景点间隙，价格轻，选择多。', '人均 15-40 元', '可快速解决', '/oneclick-trip-assets/chengdu-food-snacks.png']
    ]
  },
  hangzhou: {
    hero: 'linear-gradient(135deg, #58c9a3, #89d8e8)',
    destTitle: '🌿 杭州景点攻略',
    destSub: '西湖 · 灵隐寺 · 龙井村 · 湖滨夜景',
    routeCount: 5,
    avgTime: '2天',
    routeTitle: '推荐玩法：西湖慢走 + 灵隐祈福',
    routeDesc: '适合慢节奏路线，上午灵隐寺，下午西湖，第二天安排龙井村和茶点。',
    foodTitle: '🍵 杭州美食灵感',
    foodSub: '杭州更适合清淡茶食和本地面食，安排在西湖或龙井附近更顺。',
    spots: [
      ['西湖', '免费 · 3-4小时 · 慢游', 'linear-gradient(135deg,#84fab0,#8fd3f4)'],
      ['灵隐寺', '🎫75元 · 2-3小时 · 人文', 'linear-gradient(135deg,#d4fc79,#96e6a1)'],
      ['龙井村', '茶点 · 2小时 · 轻松', 'linear-gradient(135deg,#c1dfc4,#deecdd)']
    ],
    foods: [
      ['龙井茶点', '清淡茶食', '适合西湖或龙井村附近安排。', '人均 60-100 元', '下午茶', 'linear-gradient(135deg,#d4fc79,#96e6a1)'],
      ['片儿川', '本地面食', '适合早餐或午餐，体验杭州家常味。', '人均 20-35 元', '早餐午餐', 'linear-gradient(135deg,#f6d365,#fda085)']
    ]
  },
  xian: {
    hero: 'linear-gradient(135deg, #c79081, #dfa579)',
    destTitle: '🏛️ 西安景点攻略',
    destSub: '兵马俑 · 古城墙 · 大唐不夜城 · 回民街',
    routeCount: 5,
    avgTime: '3天',
    routeTitle: '推荐玩法：历史主线 + 夜景 + 碳水',
    routeDesc: '白天安排兵马俑和城墙，晚上去大唐不夜城，吃饭穿插肉夹馍和泡馍。',
    foodTitle: '🥙 西安美食灵感',
    foodSub: '西安美食适合做成正餐和小吃穿插，分量足，别把每顿排太满。',
    spots: [
      ['秦始皇兵马俑', '🎫120元 · 半天 · 必去', 'linear-gradient(135deg,#c79081,#dfa579)'],
      ['西安城墙', '🎫54元 · 2小时 · 骑行', 'linear-gradient(135deg,#f6d365,#fda085)'],
      ['大唐不夜城', '免费 · 夜景 · 拍照', 'linear-gradient(135deg,#667eea,#764ba2)']
    ],
    foods: [
      ['肉夹馍与凉皮', '碳水小吃', '适合景点间隙快速补能。', '人均 20-35 元', '快餐', 'linear-gradient(135deg,#f6d365,#fda085)'],
      ['羊肉泡馍', '正餐', '适合晚餐慢慢吃，注意分量较足。', '人均 45-70 元', '晚餐', 'linear-gradient(135deg,#c79081,#dfa579)']
    ]
  },
  dali: {
    hero: 'linear-gradient(135deg, #89f7fe, #66a6ff)',
    destTitle: '🏔️ 大理景点攻略',
    destSub: '洱海 · 大理古城 · 喜洲 · 苍山',
    routeCount: 4,
    avgTime: '4天',
    routeTitle: '推荐玩法：洱海骑行 + 古城慢生活',
    routeDesc: '大理适合把节奏放慢，上午骑行或看海，下午古城和咖啡，晚上轻松吃饭。',
    foodTitle: '🍄 大理美食灵感',
    foodSub: '大理适合菌子火锅、乳扇和鲜花饼，安排在古城或洱海路线里更自然。',
    spots: [
      ['洱海生态廊道', '免费 · 3-4小时 · 骑行', 'linear-gradient(135deg,#89f7fe,#66a6ff)'],
      ['大理古城', '免费 · 2-3小时 · 散步', 'linear-gradient(135deg,#a1c4fd,#c2e9fb)'],
      ['喜洲古镇', '免费 · 半日 · 田园', 'linear-gradient(135deg,#fddb92,#d1fdff)']
    ],
    foods: [
      ['菌子火锅', '云南特色', '适合晚餐，选择正规餐厅。', '人均 90-140 元', '晚餐', 'linear-gradient(135deg,#fddb92,#d1fdff)'],
      ['乳扇与鲜花饼', '轻食小吃', '适合古城散步时穿插体验。', '人均 20-40 元', '小吃', 'linear-gradient(135deg,#a1c4fd,#c2e9fb)']
    ]
  }
}

const displayCities = computed(() => {
  if (!cities.value.length) return fallbackCities
  return cities.value.map((city) => ({
    ...city,
    key: cityKeyByName(city.name),
    summaryShort: summaryShortByName(city.name)
  }))
})

const selectedGuide = computed(() => guideData[selectedCityKey.value] || guideData.chengdu)
const selectedCity = computed(() => displayCities.value.find((city) => city.key === selectedCityKey.value) || displayCities.value[0])
const currentAvatar = computed(() => findAvatar(currentUser.value?.avatarUrl))
const selectedProfileAvatar = computed(() => findAvatar(profileForm.avatarUrl))
const chengduCover = "linear-gradient(transparent 52%,rgba(0,0,0,0.68)), url('/oneclick-trip-assets/chengdu-destination.png') center 56%/cover no-repeat"

const spotCards = computed(() => {
  if (spots.value.length) {
    return spots.value.map((spot, index) => ({
      name: spot.name,
      meta: `🎫${Number(spot.ticketPrice || 0)}元 · ${spot.playHours || 2}小时 · 评分 ${spot.rating || 4.6}`,
      cover: `linear-gradient(transparent, rgba(0,0,0,0.5)), ${selectedGuide.value.spots[index % selectedGuide.value.spots.length][2]}`
    }))
  }
  return selectedGuide.value.spots.map((spot) => ({
    name: spot[0],
    meta: spot[1],
    cover: `linear-gradient(transparent, rgba(0,0,0,0.5)), ${spot[2]}`
  }))
})

const foodCards = computed(() => {
  if (foods.value.length) {
    return foods.value.map((food, index) => ({
      name: food.name,
      tag: food.category || selectedGuide.value.foods[index % selectedGuide.value.foods.length][1],
      summary: food.summary,
      price: `人均 ${food.avgPrice || 40} 元`,
      time: food.recommendedArea || '顺路安排',
      cover: food.imageUrl ? `url('/${food.imageUrl}') center/cover no-repeat` : selectedGuide.value.foods[index % selectedGuide.value.foods.length][5]
    }))
  }
  return selectedGuide.value.foods.map((food) => ({
    name: food[0],
    tag: food[1],
    summary: food[2],
    price: food[3],
    time: food[4],
    cover: food[5].startsWith('/') ? `url('${food[5]}') center/cover no-repeat` : food[5]
  }))
})

const planDays = computed(() => {
  if (plan.value?.dayPlans?.length) return plan.value.dayPlans
  return [
    {
      dayNo: 1,
      title: 'Day 1 市区经典人文',
      items: [
        { itemType: 'SPOT', title: '宽窄巷子', description: '清代古街区，适合散步和小吃。', startTime: '09:00', address: '青羊区', cost: 0 },
        { itemType: 'FOOD', title: '龙抄手', description: '午餐小吃，轻松解决。', startTime: '12:00', address: '春熙路', cost: 60 },
        { itemType: 'SPOT', title: '杜甫草堂', description: '人文历史景点。', startTime: '14:00', address: '青华路', cost: 120 }
      ]
    }
  ]
})

onMounted(async () => {
  if (isAuthenticated.value) {
    await refreshProfile()
  }
  await loadInitialData()
})

function findAvatar(avatarId) {
  return avatarOptions.find((avatar) => avatar.id === avatarId) || avatarOptions[0]
}

async function loadInitialData() {
  try {
    cities.value = await api.cities()
    backendOnline.value = true
    if (cities.value.length) {
      planForm.cityId = cities.value[0].id
      selectedCityKey.value = cityKeyByName(cities.value[0].name)
    }
  } catch {
    cities.value = fallbackCities
    backendOnline.value = false
  }
  await loadCityDetail()
}

async function loadCityDetail() {
  const city = selectedCity.value
  if (!city) return
  planForm.cityId = city.id
  if (!backendOnline.value) {
    spots.value = []
    foods.value = []
    hotels.value = []
    return
  }
  try {
    const [spotData, foodData, hotelData] = await Promise.all([
      api.spots(city.id),
      api.foods(city.id),
      api.hotels(city.id)
    ])
    spots.value = spotData
    foods.value = foodData
    hotels.value = hotelData
  } catch {
    backendOnline.value = false
    spots.value = []
    foods.value = []
    hotels.value = []
  }
}

function go(page) {
  if (page !== 'login' && !isAuthenticated.value) {
    activePage.value = 'login'
    toastText.value = '请先登录'
    return
  }
  activePage.value = page
}

async function goGuide(page, cityKey) {
  if (!isAuthenticated.value) {
    go('login')
    return
  }
  selectedCityKey.value = cityKey || selectedCityKey.value
  await loadCityDetail()
  activePage.value = page
}

function readSavedUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY))
  } catch {
    return null
  }
}

function saveUser(user) {
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(USER_KEY)
  }
}

function normalizeUser(user) {
  if (!user) return null
  return {
    ...user,
    avatarUrl: user.avatarUrl || 'avatar-compass'
  }
}

function syncProfileForm(user = currentUser.value) {
  profileForm.nickname = user?.nickname || ''
  profileForm.avatarUrl = user?.avatarUrl || 'avatar-compass'
  profileError.value = ''
}

async function refreshProfile() {
  try {
    const data = normalizeUser(await api.me())
    currentUser.value = data
    saveUser(data)
    syncProfileForm(data)
  } catch {
    setToken('')
    saveUser(null)
    currentUser.value = null
    isAuthenticated.value = false
    activePage.value = 'login'
  }
}

function fillDemoAccount(username) {
  loginForm.username = username
  loginForm.password = '123456'
  loginError.value = ''
}

async function handleLogin() {
  loginError.value = ''
  if (!loginForm.username || !loginForm.password) {
    loginError.value = '请输入账号和密码'
    return
  }
  loginLoading.value = true
  try {
    const data = await api.login({
      username: loginForm.username,
      password: loginForm.password
    })
    setToken(data.token)
    currentUser.value = normalizeUser(data)
    saveUser(currentUser.value)
    syncProfileForm(currentUser.value)
    isAuthenticated.value = true
    backendOnline.value = true
    activePage.value = 'home'
    toastText.value = `欢迎回来，${data.nickname || data.username}`
    await loadInitialData()
  } catch (error) {
    loginError.value = error.message || '登录失败，请检查账号和密码'
  } finally {
    loginLoading.value = false
  }
}

function openProfileEdit() {
  syncProfileForm()
  activePage.value = 'profileEdit'
}

async function handleProfileUpdate() {
  profileError.value = ''
  if (!profileForm.nickname) {
    profileError.value = '昵称不能为空'
    return
  }
  profileLoading.value = true
  try {
    const data = normalizeUser(await api.updateProfile({
      nickname: profileForm.nickname,
      avatarUrl: profileForm.avatarUrl
    }))
    currentUser.value = data
    saveUser(data)
    syncProfileForm(data)
    toastText.value = '个人资料已更新'
    activePage.value = 'mine'
  } catch (error) {
    profileError.value = error.message || '保存失败，请稍后再试'
  } finally {
    profileLoading.value = false
  }
}

function logout() {
  setToken('')
  saveUser(null)
  currentUser.value = null
  isAuthenticated.value = false
  plan.value = null
  aiReply.value = ''
  activePage.value = 'login'
  toastText.value = '已退出登录'
}

async function selectCityById(cityId) {
  const city = displayCities.value.find((item) => Number(item.id) === Number(cityId))
  if (city) {
    selectedCityKey.value = city.key
    await loadCityDetail()
  }
}

function togglePreference(tag) {
  const index = planForm.interests.indexOf(tag)
  if (index >= 0) {
    planForm.interests.splice(index, 1)
  } else {
    planForm.interests.push(tag)
  }
}

async function generatePlan() {
  generateLoading.value = true
  try {
    if (!backendOnline.value) {
      plan.value = null
      toastText.value = '后端未连接，当前展示原型行程'
      activePage.value = 'trip'
      return
    }
    plan.value = await api.generatePlan(planForm)
    activePage.value = 'trip'
  } catch (error) {
    toastText.value = error.message
  } finally {
    generateLoading.value = false
  }
}

async function callAiPlaceholder(message) {
  const text = message || '测试 AI 占位接口'
  try {
    if (!backendOnline.value) {
      aiReply.value = 'AI 助手暂未接入。后端未启动时，这里显示本地占位回复。'
      return
    }
    const data = await api.aiChat(text)
    aiReply.value = data.message
  } catch (error) {
    aiReply.value = error.message
  }
}

function destinationBackground(city, index) {
  if (city.key === 'chengdu') {
    return "linear-gradient(transparent 48%,rgba(0,0,0,0.72)), url('/oneclick-trip-assets/chengdu-destination.png') center/cover no-repeat"
  }
  const gradients = [
    'linear-gradient(transparent 50%,rgba(0,0,0,0.7)), linear-gradient(135deg, #4ECDC4, #44A08D)',
    'linear-gradient(transparent 50%,rgba(0,0,0,0.7)), linear-gradient(135deg, #A8E6CF, #3E8E7E)',
    'linear-gradient(transparent 50%,rgba(0,0,0,0.7)), linear-gradient(135deg, #FFD93D, #FF8C42)'
  ]
  return gradients[index % gradients.length]
}

function cityKeyByName(name) {
  if (name?.includes('杭州')) return 'hangzhou'
  if (name?.includes('西安')) return 'xian'
  if (name?.includes('大理')) return 'dali'
  return 'chengdu'
}

function summaryShortByName(name) {
  if (name?.includes('杭州')) return '人间天堂 · 西湖美景'
  if (name?.includes('西安')) return '十三朝古都 · 碳水天堂'
  if (name?.includes('大理')) return '苍山洱海 · 风花雪月'
  return '天府之国 · 美食之都'
}
</script>
