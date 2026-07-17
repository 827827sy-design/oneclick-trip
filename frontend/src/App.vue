<template>
  <div class="app-stage">
    <main class="app-shell" aria-label="一键游移动端预览">
      <div class="screen-stack">
        <section v-if="activePage === 'login'" class="screen login-screen">
          <div class="login-visual">
            <div class="login-brand">
              <span class="brand-mark"><el-icon><Compass /></el-icon></span>
              <span>一键游</span>
            </div>
            <div class="login-copy">
              <span class="eyebrow">YOUR TRIP, READY</span>
              <h1>少做攻略，<br />多去看看。</h1>
              <p>把旅行偏好说给我听，路线、吃住和预算一起安排好。</p>
            </div>
          </div>

          <form class="login-panel" @submit.prevent="handleLogin">
            <div class="panel-title">
              <div>
                <span>欢迎回来</span>
                <h2>登录后继续你的旅程</h2>
              </div>
              <el-icon><SuitcaseLine /></el-icon>
            </div>

            <label class="field">
              <span>账号</span>
              <div class="field-control">
                <el-icon><User /></el-icon>
                <input v-model.trim="loginForm.username" autocomplete="username" placeholder="请输入账号" />
              </div>
            </label>

            <label class="field">
              <span>密码</span>
              <div class="field-control">
                <el-icon><Lock /></el-icon>
                <input
                  v-model="loginForm.password"
                  autocomplete="current-password"
                  placeholder="请输入密码"
                  type="password"
                />
              </div>
            </label>

            <p v-if="loginError" class="form-error">{{ loginError }}</p>
            <button class="primary-button" type="submit" :disabled="loginLoading">
              <span>{{ loginLoading ? '正在登录' : '登录' }}</span>
              <el-icon v-if="!loginLoading"><ArrowRight /></el-icon>
              <el-icon v-else class="spin"><Loading /></el-icon>
            </button>

            <div class="demo-login">
              <span>体验账号</span>
              <button type="button" @click="fillDemoAccount('admin')">admin</button>
              <button type="button" @click="fillDemoAccount('user')">user</button>
              <small>密码均为 123456</small>
            </div>
          </form>
        </section>

        <section v-show="activePage === 'home'" class="screen home-screen">
          <header class="home-header">
            <button class="identity" type="button" @click="go('mine')">
              <span class="mini-avatar" :class="currentAvatar.className">
                <component :is="currentAvatar.icon" />
              </span>
              <span>
                <small>早上好</small>
                <strong>{{ currentUser?.nickname || '旅行者' }}</strong>
              </span>
            </button>
            <button class="icon-button" type="button" aria-label="消息">
              <el-icon><Bell /></el-icon>
              <span class="notice-dot"></span>
            </button>
          </header>

          <div class="home-hero">
            <div class="hero-shade"></div>
            <div class="hero-weather">
              <el-icon><Sunny /></el-icon>
              <span>成都 26°C</span>
              <small>适合散步</small>
            </div>
            <div class="hero-copy">
              <span class="eyebrow">AI TRAVEL CONCIERGE</span>
              <h1>今天，想去哪里？</h1>
              <p>一句话说出时间、预算和偏好。</p>
            </div>
            <form class="hero-composer" @submit.prevent="startFromPrompt">
              <button type="button" class="composer-location" aria-label="使用当前位置" @click="promptText = '从南京出发，' + promptText">
                <el-icon><Location /></el-icon>
              </button>
              <textarea
                v-model.trim="promptText"
                rows="2"
                placeholder="例如：成都 3 天，想吃得好，行程松一点"
                aria-label="描述旅行需求"
              ></textarea>
              <button type="submit" class="composer-send" aria-label="开始规划">
                <el-icon><Position /></el-icon>
              </button>
            </form>
          </div>

          <div class="preference-line">
            <div>
              <el-icon><MagicStick /></el-icon>
              <span>我记得你喜欢</span>
            </div>
            <div class="preference-tags">
              <button type="button" @click="createNewConversation('我喜欢慢节奏旅行')">慢节奏</button>
              <button type="button" @click="createNewConversation('我更喜欢体验本地美食')">本地美食</button>
              <button type="button" @click="createNewConversation('规划时尽量帮我避开排队')">少排队</button>
            </div>
          </div>

          <div class="quick-actions" aria-label="快捷入口">
            <button type="button" @click="go('chat')">
              <span class="action-icon green"><el-icon><ChatDotRound /></el-icon></span>
              <span>问 AI</span>
            </button>
            <button type="button" @click="createNewConversation('帮我规划一次旅行')">
              <span class="action-icon coral"><el-icon><MagicStick /></el-icon></span>
              <span>做行程</span>
            </button>
            <button type="button" @click="goGuide('dest', selectedCityKey)">
              <span class="action-icon blue"><el-icon><MapLocation /></el-icon></span>
              <span>看攻略</span>
            </button>
            <button type="button" @click="goGuide('food', selectedCityKey)">
              <span class="action-icon yellow"><el-icon><Food /></el-icon></span>
              <span>找美食</span>
            </button>
          </div>

          <div class="section-heading">
            <div>
              <span>旅行灵感</span>
              <h2>现在出发，正合适</h2>
            </div>
            <button type="button" @click="goGuide('dest', selectedCityKey)">全部 <el-icon><ArrowRight /></el-icon></button>
          </div>

          <div class="destination-rail">
            <button
              v-for="(city, index) in displayCities"
              :key="city.id"
              class="destination-card"
              type="button"
              :style="destinationStyle(city, index)"
              @click="goGuide('dest', city.key)"
            >
              <span v-if="index === 0" class="city-badge">本周热门</span>
              <span class="destination-copy">
                <strong>{{ city.name }}</strong>
                <small>{{ city.summaryShort }}</small>
              </span>
            </button>
          </div>

          <div class="section-heading compact">
            <div>
              <span>即将出发</span>
              <h2>成都松弛感 3 日游</h2>
            </div>
            <button type="button" @click="go('trip')">查看</button>
          </div>

          <button class="upcoming-trip" type="button" @click="go('trip')">
            <span class="trip-date"><strong>18</strong><small>JUL</small></span>
            <span class="trip-route">
              <strong>南京 <el-icon><Right /></el-icon> 成都</strong>
              <small>3 天 2 晚 · 2 人 · 预算约 3,200 元</small>
              <span class="progress-track"><i></i></span>
            </span>
            <span class="trip-ready">待预订 3</span>
          </button>
        </section>

        <section v-show="activePage === 'chat'" class="screen chat-screen">
          <AppHeader :title="activeConversationTitle" subtitle="每段对话都会单独保存" @back="go('home')">
            <button class="header-action" type="button" @click="openConversationHistory">会话记录</button>
          </AppHeader>

          <div class="profile-memory">
            <span class="memory-icon"><el-icon><UserFilled /></el-icon></span>
            <div>
              <strong>你的旅行画像</strong>
              <p>{{ profileSummary }}</p>
            </div>
            <button type="button" aria-label="查看会话记录" @click="openConversationHistory"><el-icon><EditPen /></el-icon></button>
          </div>

          <div ref="chatListRef" class="chat-list">
            <div v-if="!chatTurns.length" class="message assistant">
              <span class="assistant-avatar"><el-icon><Compass /></el-icon></span>
              <div class="message-body">
                <p>想去哪座城市？也可以直接告诉我出发地、天数和大概预算。</p>
                <div class="suggestion-row">
                  <button type="button" @click="useSuggestion('从南京去成都玩 3 天，预算 3000 元')">成都 3 天</button>
                  <button type="button" @click="useSuggestion('想找一个适合慢慢逛、好吃又不贵的城市')">帮我选城市</button>
                </div>
              </div>
            </div>

            <template v-for="turn in chatTurns" :key="turn.id">
              <div class="message user">
                <div class="message-body"><p>{{ turn.userText }}</p></div>
              </div>

              <div v-if="turn.loading" class="message assistant" aria-live="polite">
                <span class="assistant-avatar"><el-icon><Compass /></el-icon></span>
                <div class="agent-live-status">
                  <div>
                    <el-icon class="spin"><Loading /></el-icon>
                    <span>Agent 正在处理</span>
                  </div>
                  <p>识别意图并调用本次需要的工具</p>
                  <span class="loading-track"><i></i></span>
                </div>
              </div>

              <div v-else-if="turn.error" class="message assistant">
                <span class="assistant-avatar"><el-icon><Compass /></el-icon></span>
                <div class="message-body agent-error" role="alert">
                  <strong>这次没有处理成功</strong>
                  <p>{{ turn.error }}</p>
                  <button type="button" @click="retryAgentTurn(turn)">重新尝试</button>
                </div>
              </div>

              <div v-else-if="turn.response" class="message assistant">
                <span class="assistant-avatar"><el-icon><Compass /></el-icon></span>
                <article class="message-body result-message">
                  <span class="result-kicker">{{ turn.response.kicker }}</span>
                  <h3>{{ turn.response.title }}</h3>
                  <p class="agent-reply">{{ turn.response.message }}</p>

                  <div v-if="turn.response.metrics.length" class="result-stats">
                    <span v-for="metric in turn.response.metrics" :key="metric.label">
                      <small>{{ metric.label }}</small>
                      <strong>{{ metric.value }}</strong>
                    </span>
                  </div>

                  <div v-if="turn.response.tools.length" class="agent-tools" aria-label="本次调用工具">
                    <span v-for="tool in turn.response.tools" :key="tool"><el-icon><CircleCheck /></el-icon>{{ tool }}</span>
                  </div>

                  <div v-if="turn.response.planPreview.length" class="agent-plan-preview">
                    <div v-for="day in turn.response.planPreview" :key="day.dayIndex">
                      <strong>{{ day.title }}</strong>
                      <p>{{ day.items }}</p>
                    </div>
                  </div>

                  <div v-if="turn.response.interrupted" class="booking-confirmation">
                    <p>订单草稿正在等待你的确认，确认前不会提交任何预订。</p>
                    <div>
                      <button type="button" class="secondary-button quiet" @click="resumeBooking(turn, false)">取消</button>
                      <button type="button" class="secondary-button" @click="resumeBooking(turn, true)">确认预订</button>
                    </div>
                  </div>

                  <button v-else-if="turn.response.plan" class="secondary-button" type="button" @click="openAgentPlan(turn.response)">
                    查看完整行程 <el-icon><ArrowRight /></el-icon>
                  </button>
                </article>
              </div>
            </template>
          </div>

          <div class="chat-composer">
            <div class="chat-shortcuts">
              <button type="button" @click="useSuggestion('预算再省一点')">预算再省一点</button>
              <button type="button" @click="useSuggestion('不要早起')">不要早起</button>
              <button type="button" @click="useSuggestion('多安排本地美食')">多安排美食</button>
            </div>
            <form @submit.prevent="sendAgentMessage(aiInput)">
              <textarea v-model.trim="aiInput" rows="1" placeholder="继续补充你的想法" aria-label="继续补充旅行需求"></textarea>
              <button type="submit" aria-label="发送" :disabled="agentRequestRunning"><el-icon><Position /></el-icon></button>
            </form>
          </div>
        </section>

        <section v-show="activePage === 'sessions'" class="screen session-screen">
          <AppHeader title="会话记录" subtitle="继续任何一段旅行对话" @back="go('home')">
            <button class="header-action icon-only" type="button" aria-label="新建会话" @click="createNewConversation()">
              <el-icon><Plus /></el-icon>
            </button>
          </AppHeader>

          <div class="session-toolbar">
            <div>
              <strong>你的旅行对话</strong>
              <small>{{ conversationList.length }} 段会话</small>
            </div>
            <button type="button" @click="createNewConversation()"><el-icon><Plus /></el-icon> 新建对话</button>
          </div>

          <div class="session-list" :class="{ loading: conversationLoading }">
            <div v-if="conversationLoading" class="session-empty">
              <el-icon class="spin"><Loading /></el-icon>
              <p>正在读取会话记录</p>
            </div>
            <div v-else-if="!conversationList.length" class="session-empty">
              <span><el-icon><ChatDotRound /></el-icon></span>
              <h2>还没有旅行对话</h2>
              <p>新建一个窗口，天气、路线和行程讨论都会保存在里面。</p>
              <button type="button" @click="createNewConversation()">开始第一段对话</button>
            </div>
            <template v-else>
              <article
                v-for="conversation in conversationList"
                :key="conversation.conversationId"
                class="session-card"
                :class="{ active: conversation.conversationId === currentConversationId }"
              >
                <button class="session-main" type="button" @click="openConversation(conversation.conversationId)">
                  <span class="session-icon"><el-icon><ChatDotRound /></el-icon></span>
                  <span class="session-copy">
                    <strong>{{ conversation.title }}</strong>
                    <p>{{ conversation.lastMessagePreview || '还没有消息，点开继续聊聊' }}</p>
                    <small>{{ formatConversationTime(conversation.updateTime) }} · {{ conversation.messageCount }} 条消息</small>
                  </span>
                </button>
                <button class="session-delete" type="button" aria-label="删除会话" @click="deleteConversation(conversation)">
                  <el-icon><Delete /></el-icon>
                </button>
              </article>
            </template>
          </div>
        </section>

        <section v-show="activePage === 'trip'" class="screen trip-screen">
          <div class="trip-cover">
            <div class="trip-cover-actions">
              <button class="image-button" type="button" aria-label="返回" @click="go('home')"><el-icon><Back /></el-icon></button>
              <div>
                <button class="image-button" type="button" aria-label="收藏" @click="showToast('已收藏这份行程')"><el-icon><Star /></el-icon></button>
                <button class="image-button" type="button" aria-label="更多"><el-icon><MoreFilled /></el-icon></button>
              </div>
            </div>
            <div class="trip-cover-copy">
              <span class="plan-status"><i></i> 方案已完成</span>
              <h1>{{ plan?.title || '成都松弛感 3 日游' }}</h1>
              <p>{{ plan?.days || 3 }} 天 {{ (plan?.days || 3) - 1 }} 晚 · {{ plan?.peopleCount || 2 }} 人 · {{ budgetLabel }}</p>
            </div>
          </div>

          <div class="trip-overview">
            <div><span><el-icon><Wallet /></el-icon></span><small>预计总花费</small><strong>¥{{ plan?.totalBudget || 3180 }}</strong></div>
            <div><span><el-icon><Timer /></el-icon></span><small>日均游玩</small><strong>{{ averageDailyHours }}</strong></div>
            <div><span><el-icon><Tickets /></el-icon></span><small>待预订</small><strong>{{ pendingBookingCount }} 项</strong></div>
          </div>

          <div class="agent-note">
            <span><el-icon><MagicStick /></el-icon></span>
            <div>
              <strong>这样安排更适合你</strong>
              <p>{{ planReasonText }}</p>
            </div>
            <button type="button" aria-label="让 AI 修改行程" @click="go('chat')"><el-icon><EditPen /></el-icon></button>
          </div>

          <div class="day-tabs" role="tablist" aria-label="选择行程日期">
            <button
              v-for="day in planDays"
              :key="day.dayNo"
              type="button"
              role="tab"
              :aria-selected="selectedDayNo === day.dayNo"
              :class="{ active: selectedDayNo === day.dayNo }"
              @click="selectedDayNo = day.dayNo"
            >
              <small>DAY {{ day.dayNo }}</small>
              <strong>{{ dayWeekday(day) }}</strong>
            </button>
          </div>

          <div class="day-summary">
            <div>
              <span>{{ activeDay.title }}</span>
              <h2>{{ activeDay.theme || dayTheme(activeDay.dayNo) }}</h2>
            </div>
            <span class="weather-chip"><el-icon><Sunny /></el-icon>{{ plan?.weatherSummary || '天气待确认' }}</span>
          </div>

          <div class="itinerary">
            <article v-for="(item, index) in activeDay.items" :key="item.title + index" class="itinerary-item">
              <time>{{ item.startTime }}</time>
              <span class="timeline-node" :class="item.itemType?.toLowerCase()">
                <el-icon><component :is="itemIcon(item.itemType)" /></el-icon>
              </span>
              <div class="itinerary-content">
                <div class="item-heading">
                  <div>
                    <span>{{ itemTypeLabel(item.itemType) }}</span>
                    <h3>{{ item.title }}</h3>
                  </div>
                  <strong>¥{{ item.cost || 0 }}</strong>
                </div>
                <p>{{ item.description }}</p>
                <div class="item-meta">
                  <span><el-icon><Location /></el-icon>{{ item.address || '沿路线顺路到达' }}</span>
                  <span><el-icon><Timer /></el-icon>{{ item.duration || '约 2 小时' }}</span>
                </div>
                <button
                  v-if="item.bookable ?? isBookable(item.itemType)"
                  class="booking-trigger"
                  type="button"
                  @click="toggleBooking(item.title)"
                >
                  <span>{{ bookingItem === item.title ? '收起预订' : bookingLabel(item.itemType) }}</span>
                  <el-icon :class="{ rotate: bookingItem === item.title }"><ArrowDown /></el-icon>
                </button>
                <div v-if="bookingItem === item.title" class="booking-panel">
                  <div>
                    <span class="booking-provider">预订渠道待接入</span>
                    <strong>{{ bookingOffer(item) }}</strong>
                    <small>可退改 · 下单前再次确认</small>
                  </div>
                  <button type="button" @click="confirmBooking(item)">选择</button>
                </div>
              </div>
            </article>
          </div>

          <div class="trip-bottom-action">
            <button type="button" @click="go('chat')"><el-icon><ChatDotRound /></el-icon><span>让 AI 修改</span></button>
            <button type="button" class="book-all" @click="showToast(`已生成 ${pendingBookingCount} 项预订清单`)">查看预订清单</button>
          </div>
        </section>

        <section v-show="activePage === 'dest'" class="screen explore-screen">
          <AppHeader title="发现" subtitle="景点攻略" @back="go('home')">
            <button class="header-action icon-only" type="button" aria-label="搜索"><el-icon><Search /></el-icon></button>
          </AppHeader>

          <div class="explore-tabs">
            <button class="active" type="button">景点攻略</button>
            <button type="button" @click="goGuide('food', selectedCityKey)">本地美食</button>
          </div>

          <div class="city-switch">
            <button
              v-for="city in displayCities"
              :key="city.id"
              type="button"
              :class="{ active: selectedCityKey === city.key }"
              @click="goGuide('dest', city.key)"
            >{{ city.name }}</button>
          </div>

          <div class="guide-hero" :style="{ backgroundImage: guideHeroBackground }">
            <div>
              <span>LOCAL GUIDE</span>
              <h1>{{ selectedGuide.destTitle }}</h1>
              <p>{{ selectedGuide.destSub }}</p>
            </div>
          </div>

          <div class="guide-facts">
            <div><strong>{{ spots.length || selectedGuide.spots.length }}</strong><span>精选景点</span></div>
            <div><strong>{{ selectedGuide.routeCount }}</strong><span>推荐路线</span></div>
            <div><strong>{{ selectedGuide.avgTime }}</strong><span>适合游玩</span></div>
          </div>

          <div class="section-heading compact">
            <div><span>不绕路的玩法</span><h2>{{ selectedGuide.routeTitle }}</h2></div>
          </div>
          <p class="route-description">{{ selectedGuide.routeDesc }}</p>

          <div class="spot-list">
            <article v-for="(spot, index) in spotCards" :key="spot.name">
              <div class="spot-image" :style="{ backgroundImage: spot.cover }">
                <span>{{ String(index + 1).padStart(2, '0') }}</span>
              </div>
              <div>
                <span>{{ index === 0 ? '第一次来必去' : '顺路安排' }}</span>
                <h3>{{ spot.name }}</h3>
                <p>{{ spot.meta }}</p>
                <button type="button" @click="showToast('已加入候选行程')">加入行程 <el-icon><Plus /></el-icon></button>
              </div>
            </article>
          </div>
        </section>

        <section v-show="activePage === 'food'" class="screen explore-screen">
          <AppHeader title="发现" subtitle="本地美食" @back="go('home')">
            <button class="header-action icon-only" type="button" aria-label="搜索"><el-icon><Search /></el-icon></button>
          </AppHeader>

          <div class="explore-tabs">
            <button type="button" @click="goGuide('dest', selectedCityKey)">景点攻略</button>
            <button class="active" type="button">本地美食</button>
          </div>

          <div class="city-switch">
            <button
              v-for="city in displayCities"
              :key="city.id"
              type="button"
              :class="{ active: selectedCityKey === city.key }"
              @click="goGuide('food', city.key)"
            >{{ city.name }}</button>
          </div>

          <div class="food-intro">
            <span><el-icon><Food /></el-icon></span>
            <div><small>为你的路线挑选</small><h1>{{ selectedGuide.foodTitle }}</h1><p>{{ selectedGuide.foodSub }}</p></div>
          </div>

          <div class="food-list">
            <article v-for="food in foodCards" :key="food.name">
              <div class="food-image" :style="{ backgroundImage: food.cover }">
                <span>{{ food.tag }}</span>
              </div>
              <div class="food-content">
                <div><h3>{{ food.name }}</h3><strong>{{ food.price }}</strong></div>
                <p>{{ food.summary }}</p>
                <span><el-icon><Location /></el-icon>{{ food.time }}</span>
                <button type="button" @click="showToast('已加入美食候选')">加入行程 <el-icon><Plus /></el-icon></button>
              </div>
            </article>
          </div>
        </section>

        <section v-show="activePage === 'mine'" class="screen mine-screen">
          <header class="mine-header">
            <div class="mine-title"><span>我的</span><button class="icon-button" type="button" aria-label="设置"><el-icon><Setting /></el-icon></button></div>
            <button class="profile-summary" type="button" @click="openProfileEdit">
              <span class="profile-avatar" :class="currentAvatar.className"><component :is="currentAvatar.icon" /></span>
              <span><strong>{{ currentUser?.nickname || '旅行者' }}</strong><small>@{{ currentUser?.username || 'traveler' }}</small></span>
              <el-icon><ArrowRight /></el-icon>
            </button>
            <div class="profile-tags"><span>慢节奏</span><span>吃货</span><span>城市漫游</span></div>
          </header>

          <div class="travel-stats">
            <div><strong>3</strong><span>我的行程</span></div>
            <div><strong>12</strong><span>收藏地点</span></div>
            <div><strong>4</strong><span>去过城市</span></div>
          </div>

          <div class="mine-section">
            <div class="section-heading compact"><div><span>下一次出发</span><h2>成都 · 7 月 18 日</h2></div><button type="button" @click="go('trip')">查看</button></div>
            <div class="mini-route">
              <span class="trip-date"><strong>18</strong><small>JUL</small></span>
              <div><strong>南京 <el-icon><Right /></el-icon> 成都</strong><small>3 天 2 晚 · 待预订 3 项</small></div>
              <span class="route-status">准备中</span>
            </div>
          </div>

          <div class="mine-menu">
            <button type="button" @click="showToast('订单中心为演示入口')"><span><el-icon><Tickets /></el-icon>我的订单</span><el-icon><ArrowRight /></el-icon></button>
            <button type="button" @click="showToast('收藏夹为演示入口')"><span><el-icon><Star /></el-icon>我的收藏</span><el-icon><ArrowRight /></el-icon></button>
            <button type="button" @click="go('chat')"><span><el-icon><UserFilled /></el-icon>旅行偏好</span><el-icon><ArrowRight /></el-icon></button>
            <button type="button" @click="showToast('消息中心为演示入口')"><span><el-icon><Bell /></el-icon>消息通知</span><el-icon><ArrowRight /></el-icon></button>
          </div>

          <button class="logout-button" type="button" @click="logout"><el-icon><SwitchButton /></el-icon>退出登录</button>
        </section>

        <section v-show="activePage === 'profileEdit'" class="screen profile-edit-screen">
          <AppHeader title="编辑资料" subtitle="保存后同步更新" @back="go('mine')">
            <button class="header-action" type="button" :disabled="profileLoading" @click="handleProfileUpdate">保存</button>
          </AppHeader>

          <div class="avatar-preview">
            <span class="profile-avatar large" :class="selectedProfileAvatar.className">
              <component :is="selectedProfileAvatar.icon" />
            </span>
            <div><strong>{{ profileForm.nickname || '旅行者' }}</strong><small>选择一个代表你的旅行头像</small></div>
          </div>

          <form class="profile-form" @submit.prevent="handleProfileUpdate">
            <fieldset class="form-section">
              <legend>昵称</legend>
              <label class="single-input">
                <input v-model.trim="profileForm.nickname" maxlength="20" placeholder="输入昵称" />
                <span>{{ profileForm.nickname.length }}/20</span>
              </label>
              <p v-if="profileError" class="form-error">{{ profileError }}</p>
            </fieldset>

            <fieldset class="form-section">
              <legend>头像</legend>
              <div class="avatar-grid">
                <button
                  v-for="avatar in avatarOptions"
                  :key="avatar.id"
                  type="button"
                  :class="{ active: profileForm.avatarUrl === avatar.id }"
                  @click="profileForm.avatarUrl = avatar.id"
                >
                  <span class="profile-avatar" :class="avatar.className"><component :is="avatar.icon" /></span>
                  <small>{{ avatar.label }}</small>
                  <el-icon v-if="profileForm.avatarUrl === avatar.id"><CircleCheckFilled /></el-icon>
                </button>
              </div>
            </fieldset>
          </form>
        </section>
      </div>

      <nav v-if="showTabbar" class="tabbar" aria-label="主要导航">
        <button type="button" :class="{ active: activePage === 'home' }" @click="go('home')">
          <el-icon><House /></el-icon><span>首页</span>
        </button>
        <button type="button" class="ai-tab" :class="{ active: activePage === 'chat' || activePage === 'sessions' }" @click="go('chat')">
          <el-icon><MagicStick /></el-icon><span>AI 助手</span>
        </button>
        <button type="button" :class="{ active: activePage === 'trip' }" @click="go('trip')">
          <el-icon><MapLocation /></el-icon><span>行程</span>
        </button>
        <button type="button" :class="{ active: activePage === 'mine' }" @click="go('mine')">
          <el-icon><User /></el-icon><span>我的</span>
        </button>
      </nav>

      <Transition name="toast">
        <div v-if="toastText" class="toast-message" role="status">{{ toastText }}</div>
      </Transition>
    </main>
  </div>
</template>

<script setup>
import { computed, defineComponent, h, nextTick, onMounted, reactive, ref } from 'vue'
import {
  ArrowDown,
  ArrowRight,
  Back,
  Bell,
  Bicycle,
  Calendar,
  Camera,
  ChatDotRound,
  Check,
  CircleCheck,
  CircleCheckFilled,
  Compass,
  Delete,
  EditPen,
  Food,
  House,
  Loading,
  Location,
  Lock,
  MagicStick,
  MapLocation,
  MoreFilled,
  OfficeBuilding,
  Plus,
  Position,
  Refresh,
  Right,
  Search,
  Setting,
  Star,
  Sunny,
  SuitcaseLine,
  SwitchButton,
  Tickets,
  Timer,
  User,
  UserFilled,
  Van,
  Wallet
} from '@element-plus/icons-vue'
import { api, getAiConversationId, getToken, resetAiConversationId, setAiConversationId, setToken } from './api/client'

const USER_KEY = 'oneclick_trip_user'

const AppHeader = defineComponent({
  props: {
    title: { type: String, required: true },
    subtitle: { type: String, default: '' }
  },
  emits: ['back'],
  setup(props, { emit, slots }) {
    return () =>
      h('header', { class: 'app-header' }, [
        h('button', { class: 'header-back', type: 'button', 'aria-label': '返回', onClick: () => emit('back') }, [h(Back)]),
        h('div', { class: 'header-title' }, [h('strong', props.title), props.subtitle ? h('small', props.subtitle) : null]),
        h('div', { class: 'header-slot' }, slots.default ? slots.default() : null)
      ])
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
const toastText = ref('')
const loginLoading = ref(false)
const loginError = ref('')
const profileLoading = ref(false)
const profileError = ref('')
const promptText = ref('')
const chatTurns = ref([])
const conversationList = ref([])
const conversationLoading = ref(false)
const currentConversationId = ref(getAiConversationId())
const agentRequestRunning = ref(false)
const latestAgentPreferences = ref(null)
const chatListRef = ref(null)
const selectedDayNo = ref(1)
const bookingItem = ref('')
let toastTimer = null
let chatTurnId = 0

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

const budgetOptions = [
  { value: 'LOW', label: '省着玩', hint: '¥800/天内' },
  { value: 'MEDIUM', label: '刚刚好', hint: '¥800-1500/天' },
  { value: 'HIGH', label: '住好一点', hint: '¥1500/天起' }
]

const preferenceTags = [
  { label: '美食', icon: Food },
  { label: '轻松', icon: Refresh },
  { label: '人文', icon: OfficeBuilding },
  { label: '拍照', icon: Camera },
  { label: '亲子', icon: UserFilled },
  { label: '自然', icon: Bicycle }
]

const avatarOptions = [
  { id: 'avatar-compass', icon: Compass, label: '探索者', className: 'avatar-teal' },
  { id: 'avatar-backpack', icon: SuitcaseLine, label: '背包客', className: 'avatar-green' },
  { id: 'avatar-camera', icon: Camera, label: '摄影师', className: 'avatar-blue' },
  { id: 'avatar-panda', icon: UserFilled, label: '慢游派', className: 'avatar-warm' },
  { id: 'avatar-mountain', icon: MapLocation, label: '山野派', className: 'avatar-lime' },
  { id: 'avatar-noodle', icon: Food, label: '美食家', className: 'avatar-coral' }
]

const fallbackCities = [
  { id: 1, key: 'chengdu', name: '成都', province: '四川', summaryShort: '美食与松弛感' },
  { id: 2, key: 'hangzhou', name: '杭州', province: '浙江', summaryShort: '湖边慢慢走' },
  { id: 3, key: 'xian', name: '西安', province: '陕西', summaryShort: '古都与碳水' },
  { id: 4, key: 'dali', name: '大理', province: '云南', summaryShort: '吹风看洱海' }
]

const guideData = {
  chengdu: {
    image: '/oneclick-trip-assets/chengdu-destination.png',
    destTitle: '成都景点攻略',
    destSub: '市井烟火、熊猫与古蜀文化，适合慢慢吃、慢慢逛。',
    routeCount: 6,
    avgTime: '3 天',
    routeTitle: '市区经典 + 熊猫 + 都江堰',
    routeDesc: '第一天把古街与人文景点串起来，第二天早些看熊猫，第三天去都江堰，返程前不赶路。',
    foodTitle: '成都吃什么',
    foodSub: '正餐与小吃错开，辣味与清甜交替，三天也不会吃得太累。',
    spots: [
      ['大熊猫基地', '门票 55 元 · 建议早去 · 3-4 小时', '/oneclick-trip-assets/chengdu-panda-base.png'],
      ['宽窄巷子', '免费 · 市井街区 · 2 小时', '/oneclick-trip-assets/chengdu-kuanzhai-alley.png'],
      ['杜甫草堂', '门票 60 元 · 人文历史 · 2 小时', '/oneclick-trip-assets/chengdu-dufu-cottage.png']
    ],
    foods: [
      ['火锅与串串', '晚餐首选', '适合留给抵达后的第一晚，辣度可选。', '人均 ¥80-120', '春熙路附近', '/oneclick-trip-assets/chengdu-food-hotpot.png'],
      ['担担面与冰粉', '小吃组合', '景点之间快速补能，咸辣之后来一碗冰粉。', '人均 ¥20-45', '宽窄巷子附近', '/oneclick-trip-assets/chengdu-food-snacks.png']
    ]
  },
  hangzhou: {
    image: '/oneclick-trip-assets/hangzhou-west-lake.png',
    destTitle: '杭州景点攻略',
    destSub: '西湖、灵隐与茶山，清晨和傍晚都值得留白。',
    routeCount: 5,
    avgTime: '2 天',
    routeTitle: '灵隐祈福 + 西湖慢走',
    routeDesc: '上午去灵隐寺，下午沿西湖走到日落；第二天把龙井村与茶点安排在一起。',
    foodTitle: '杭州吃什么',
    foodSub: '清淡茶食与本地面食更适合穿插在湖边路线里。',
    spots: [
      ['西湖', '免费 · 湖边慢游 · 3-4 小时', '/oneclick-trip-assets/hangzhou-west-lake.png'],
      ['灵隐寺', '门票 75 元 · 人文 · 2-3 小时', '/oneclick-trip-assets/hangzhou-lingyin-temple.png'],
      ['龙井村', '茶园慢游 · 2 小时', '/oneclick-trip-assets/hangzhou-longjing-village.png']
    ],
    foods: [
      ['龙井茶点', '下午茶', '在龙井村停下来喝一盏茶。', '人均 ¥60-100', '龙井村', '/oneclick-trip-assets/hangzhou-longjing-snacks.png'],
      ['片儿川', '本地面食', '早餐或午餐都很合适。', '人均 ¥20-35', '湖滨附近', '/oneclick-trip-assets/hangzhou-pianerchuan.png']
    ]
  },
  xian: {
    image: '/oneclick-trip-assets/xian-city-wall.png',
    destTitle: '西安景点攻略',
    destSub: '古城历史与夜游体验集中，适合一条主线走到底。',
    routeCount: 5,
    avgTime: '3 天',
    routeTitle: '兵马俑 + 城墙 + 长安夜色',
    routeDesc: '白天安排历史主线，傍晚登城墙，夜晚去大唐不夜城，中间穿插本地小吃。',
    foodTitle: '西安吃什么',
    foodSub: '碳水分量足，正餐与小吃别排得太密。',
    spots: [
      ['秦始皇兵马俑', '门票 120 元 · 半日 · 必去', '/oneclick-trip-assets/xian-terracotta-army.png'],
      ['西安城墙', '门票 54 元 · 骑行 · 2 小时', '/oneclick-trip-assets/xian-city-wall.png'],
      ['大唐不夜城', '免费 · 夜景 · 2-3 小时', '/oneclick-trip-assets/xian-datang-mall.png']
    ],
    foods: [
      ['肉夹馍与凉皮', '碳水组合', '适合景点之间快速补能。', '人均 ¥20-35', '钟楼附近', '/oneclick-trip-assets/xian-roujiamo-liangpi.png'],
      ['羊肉泡馍', '本地正餐', '留给时间充裕的一顿晚餐。', '人均 ¥45-70', '洒金桥附近', '/oneclick-trip-assets/xian-yangrou-paomo.png']
    ]
  },
  dali: {
    image: '/oneclick-trip-assets/dali-erhai.png',
    destTitle: '大理景点攻略',
    destSub: '洱海、古城与村落，把节奏放慢才是正确打开方式。',
    routeCount: 4,
    avgTime: '4 天',
    routeTitle: '洱海骑行 + 古城慢生活',
    routeDesc: '上午看海或骑行，下午逛古城与咖啡店，傍晚把时间留给风和日落。',
    foodTitle: '大理吃什么',
    foodSub: '菌子、乳扇与鲜花饼，顺着古城和洱海路线安排。',
    spots: [
      ['洱海生态廊道', '免费 · 骑行 · 3-4 小时', '/oneclick-trip-assets/dali-erhai.png'],
      ['大理古城', '免费 · 散步 · 2-3 小时', '/oneclick-trip-assets/dali-ancient-city.png'],
      ['喜洲古镇', '免费 · 田园 · 半日', '/oneclick-trip-assets/dali-xizhou-town.png']
    ],
    foods: [
      ['菌子火锅', '云南特色', '选择正规餐厅并遵循煮制时间。', '人均 ¥90-140', '大理古城', '/oneclick-trip-assets/dali-mushroom-hotpot.png'],
      ['乳扇与鲜花饼', '散步小吃', '适合古城路线中途品尝。', '人均 ¥20-40', '人民路附近', '/oneclick-trip-assets/dali-rushan-flower-cake.png']
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
const showTabbar = computed(() => ['home', 'dest', 'food', 'trip', 'sessions', 'mine'].includes(activePage.value))
const activeConversationTitle = computed(() => {
  return conversationList.value.find((item) => item.conversationId === currentConversationId.value)?.title || 'AI 旅行助手'
})
const budgetLabel = computed(() => budgetOptions.find((option) => option.value === planForm.budgetLevel)?.label || '预算适中')
const profileSummary = computed(() => {
  const preferences = latestAgentPreferences.value
  if (!preferences) return '还没有形成长期偏好，聊几句后我会逐步记住'

  const labels = [...(preferences.liked_tags || [])]
  if (preferences.pace) labels.push(preferences.pace === 'relaxed' ? '慢节奏' : preferences.pace)
  if (preferences.typical_budget_scope === 'per_person') labels.push('习惯看人均预算')
  return labels.length ? labels.slice(0, 4).join(' · ') : '偏好仍在了解中，本次明确需求会优先'
})
const guideHeroBackground = computed(() => {
  return "linear-gradient(180deg, rgba(20, 34, 29, 0.08), rgba(20, 34, 29, 0.72)), url('" + selectedGuide.value.image + "')"
})

const spotCards = computed(() => {
  if (spots.value.length) {
    return spots.value.map((spot, index) => ({
      name: spot.name,
      meta: '门票 ' + Number(spot.ticketPrice || 0) + ' 元 · ' + (spot.playHours || 2) + ' 小时 · 评分 ' + (spot.rating || 4.6),
      cover: "linear-gradient(180deg, rgba(20, 34, 29, 0.04), rgba(20, 34, 29, 0.4)), url('" + selectedGuide.value.spots[index % selectedGuide.value.spots.length][2] + "')"
    }))
  }
  return selectedGuide.value.spots.map((spot) => ({
    name: spot[0],
    meta: spot[1],
    cover: "linear-gradient(180deg, rgba(20, 34, 29, 0.04), rgba(20, 34, 29, 0.4)), url('" + spot[2] + "')"
  }))
})

const foodCards = computed(() => {
  if (foods.value.length) {
    return foods.value.map((food, index) => ({
      name: food.name,
      tag: food.category || selectedGuide.value.foods[index % selectedGuide.value.foods.length][1],
      summary: food.summary,
      price: '人均 ¥' + (food.avgPrice || 40),
      time: food.recommendedArea || '顺路安排',
      cover: "url('" + (food.imageUrl ? '/' + food.imageUrl : selectedGuide.value.foods[index % selectedGuide.value.foods.length][5]) + "')"
    }))
  }
  return selectedGuide.value.foods.map((food) => ({
    name: food[0],
    tag: food[1],
    summary: food[2],
    price: food[3],
    time: food[4],
    cover: "url('" + food[5] + "')"
  }))
})

const planDays = computed(() => {
  if (plan.value?.dayPlans?.length) return plan.value.dayPlans
  return [
    {
      dayNo: 1,
      title: 'Day 1 · 7 月 18 日',
      items: [
        { itemType: 'TRANSPORT', title: '高铁抵达成都东站', description: '抵达后乘地铁前往春熙路，先寄存行李。', startTime: '09:42', address: '成都东站', duration: '约 35 分钟', cost: 12 },
        { itemType: 'FOOD', title: '张老二凉粉', description: '用甜水面、凉粉和冰粉作为成都第一顿，分量不会太撑。', startTime: '11:30', address: '文殊院附近', duration: '约 1 小时', cost: 46 },
        { itemType: 'SPOT', title: '文殊院与周边街巷', description: '先走安静的人文路线，再慢慢逛到人民公园。', startTime: '13:00', address: '青羊区文殊院街', duration: '约 2.5 小时', cost: 0 },
        { itemType: 'HOTEL', title: '春熙路设计酒店', description: '靠近地铁 2 号线，去第二天的熊猫基地更顺。', startTime: '17:10', address: '锦江区春熙路', duration: '入住 2 晚', cost: 528 }
      ]
    },
    {
      dayNo: 2,
      title: 'Day 2 · 7 月 19 日',
      items: [
        { itemType: 'SPOT', title: '成都大熊猫繁育研究基地', description: '上午活跃度更高，优先看太阳产房与成年熊猫区。', startTime: '08:30', address: '成华区熊猫大道', duration: '约 3.5 小时', cost: 55 },
        { itemType: 'FOOD', title: '建设路小吃街', description: '选三到四样小吃共享，避免下午太撑。', startTime: '13:10', address: '成华区建设路', duration: '约 1.5 小时', cost: 90 },
        { itemType: 'SPOT', title: '东郊记忆', description: '工业风街区适合散步与拍照，傍晚光线更柔和。', startTime: '15:10', address: '成华区建设南支路', duration: '约 2 小时', cost: 0 },
        { itemType: 'FOOD', title: '玉林社区火锅', description: '选择鸳鸯锅，提前在线取号可减少等待。', startTime: '19:00', address: '武侯区玉林路', duration: '约 2 小时', cost: 220 }
      ]
    },
    {
      dayNo: 3,
      title: 'Day 3 · 7 月 20 日',
      items: [
        { itemType: 'TRANSPORT', title: '成都到都江堰城际列车', description: '提前 35 分钟出发到犀浦站，刷证进站。', startTime: '09:10', address: '犀浦站', duration: '约 30 分钟', cost: 20 },
        { itemType: 'SPOT', title: '都江堰景区', description: '从秦堰楼方向进入，路线以下行为主，更省体力。', startTime: '10:20', address: '都江堰市公园路', duration: '约 4 小时', cost: 80 },
        { itemType: 'FOOD', title: '南桥河鲜与小吃', description: '返程前在南桥附近吃一顿，不再额外绕路。', startTime: '14:50', address: '都江堰南桥', duration: '约 1 小时', cost: 96 },
        { itemType: 'TRANSPORT', title: '返回成都并前往车站', description: '预留 90 分钟机动时间，行李已寄存在酒店。', startTime: '16:20', address: '离堆公园站', duration: '约 1.5 小时', cost: 26 }
      ]
    }
  ]
})

const activeDay = computed(() => planDays.value.find((day) => Number(day.dayNo) === Number(selectedDayNo.value)) || planDays.value[0])
const pendingBookingCount = computed(() => {
  if (Number.isFinite(plan.value?.bookableCount)) return plan.value.bookableCount
  return planDays.value.reduce(
    (total, day) => total + (day.items || []).filter((item) => item.bookable ?? isBookable(item.itemType)).length,
    0
  )
})
const averageDailyHours = computed(() => {
  const totalMinutes = planDays.value.reduce(
    (total, day) => total + (day.items || []).reduce((dayTotal, item) => dayTotal + itemDurationMinutes(item), 0),
    0
  )
  if (!totalMinutes || !planDays.value.length) return '待核对'
  return `${(totalMinutes / planDays.value.length / 60).toFixed(1)} 小时`
})
const planReasonText = computed(() => {
  return plan.value?.agentReason
    || plan.value?.summary
    || '行程已按地点顺序与预算整理，可以继续让 AI 调整。'
})

onMounted(async () => {
  if (isAuthenticated.value) {
    await refreshProfile()
    if (isAuthenticated.value) await loadConversations()
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

async function go(page) {
  if (page !== 'login' && !isAuthenticated.value) {
    activePage.value = 'login'
    showToast('请先登录')
    return
  }
  if (page === 'chat') {
    if (currentConversationId.value) {
      await openConversation(currentConversationId.value)
    } else {
      await createNewConversation()
    }
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
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user))
  else localStorage.removeItem(USER_KEY)
}

function normalizeUser(user) {
  if (!user) return null
  return { ...user, avatarUrl: user.avatarUrl || 'avatar-compass' }
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
    const data = await api.login({ username: loginForm.username, password: loginForm.password })
    setToken(data.token)
    currentUser.value = normalizeUser(data)
    saveUser(currentUser.value)
    syncProfileForm(currentUser.value)
    isAuthenticated.value = true
    backendOnline.value = true
    activePage.value = 'home'
    showToast('欢迎回来，' + (data.nickname || data.username))
    await loadConversations()
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
    const data = normalizeUser(await api.updateProfile({ nickname: profileForm.nickname, avatarUrl: profileForm.avatarUrl }))
    currentUser.value = data
    saveUser(data)
    syncProfileForm(data)
    showToast('个人资料已更新')
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
  chatTurns.value = []
  conversationList.value = []
  currentConversationId.value = ''
  resetAiConversationId()
  latestAgentPreferences.value = null
  activePage.value = 'login'
  showToast('已退出登录')
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
  if (index >= 0) planForm.interests.splice(index, 1)
  else planForm.interests.push(tag)
}

async function generatePlan() {
  generateLoading.value = true
  try {
    if (backendOnline.value) plan.value = await api.generatePlan(planForm)
    selectedDayNo.value = 1
    activePage.value = 'trip'
    showToast(backendOnline.value ? '行程已生成' : '已生成演示行程')
  } catch (error) {
    showToast(error.message || '生成失败，请稍后重试')
  } finally {
    generateLoading.value = false
  }
}

async function startFromPrompt() {
  const message = promptText.value || '帮我规划一次轻松的成都旅行'
  promptText.value = ''
  await createNewConversation(message)
}

function useSuggestion(message) {
  aiInput.value = message
  sendAgentMessage(message)
}

async function sendAgentMessage(message) {
  const text = (message || '').trim()
  if (!text || agentRequestRunning.value) return
  if (!currentConversationId.value) {
    const created = await api.createAiConversation()
    setCurrentConversation(created.conversationId)
    conversationList.value.unshift(created)
  }

  const turn = {
    id: ++chatTurnId,
    userText: text,
    loading: true,
    error: '',
    response: null
  }
  chatTurns.value.push(turn)
  aiInput.value = ''
  await scrollChatToBottom()
  await runAgentTurn(turn)
}

async function runAgentTurn(turn) {
  agentRequestRunning.value = true
  turn.loading = true
  turn.error = ''
  try {
    const data = await api.aiChat(turn.userText)
    turn.response = normalizeAgentResponse(data)
    latestAgentPreferences.value = data?.agentState?.user_preferences || latestAgentPreferences.value
    backendOnline.value = true
    await loadConversations(false)
  } catch (error) {
    turn.error = error.message || 'Agent 服务暂时不可用，请稍后再试'
  } finally {
    turn.loading = false
    agentRequestRunning.value = false
    await scrollChatToBottom()
  }
}

async function retryAgentTurn(turn) {
  if (agentRequestRunning.value) return
  turn.response = null
  await runAgentTurn(turn)
}

async function resumeBooking(turn, confirmed) {
  if (agentRequestRunning.value) return
  agentRequestRunning.value = true
  turn.loading = true
  turn.error = ''
  try {
    const data = await api.aiResume(confirmed)
    turn.response = normalizeAgentResponse(data)
    latestAgentPreferences.value = data?.agentState?.user_preferences || latestAgentPreferences.value
    await loadConversations(false)
  } catch (error) {
    turn.error = error.message || '预订确认失败，请稍后重试'
    turn.response = null
  } finally {
    turn.loading = false
    agentRequestRunning.value = false
    await scrollChatToBottom()
  }
}

async function loadConversations(showLoading = true) {
  if (!isAuthenticated.value) return
  if (showLoading) conversationLoading.value = true
  try {
    conversationList.value = await api.aiConversations()
    if (currentConversationId.value && !conversationList.value.some((item) => item.conversationId === currentConversationId.value)) {
      setCurrentConversation('')
      chatTurns.value = []
    }
  } catch (error) {
    showToast(error.message || '会话记录加载失败')
  } finally {
    if (showLoading) conversationLoading.value = false
  }
}

async function openConversationHistory() {
  activePage.value = 'sessions'
  await loadConversations()
}

async function createNewConversation(initialMessage = '') {
  if (agentRequestRunning.value) return
  try {
    const conversation = await api.createAiConversation()
    setCurrentConversation(conversation.conversationId)
    chatTurns.value = []
    conversationList.value = [conversation, ...conversationList.value.filter((item) => item.conversationId !== conversation.conversationId)]
    activePage.value = 'chat'
    if (initialMessage) await sendAgentMessage(initialMessage)
  } catch (error) {
    showToast(error.message || '新建会话失败')
  }
}

async function openConversation(conversationId) {
  if (!conversationId || agentRequestRunning.value) return
  conversationLoading.value = true
  try {
    const detail = await api.aiConversation(conversationId)
    setCurrentConversation(conversationId)
    chatTurns.value = messagesToChatTurns(detail.messages || [])
    activePage.value = 'chat'
    await scrollChatToBottom()
  } catch (error) {
    showToast(error.message || '会话打开失败')
  } finally {
    conversationLoading.value = false
  }
}

async function deleteConversation(conversation) {
  const confirmed = window.confirm(`确定删除“${conversation.title}”吗？删除后将不再出现在会话记录中。`)
  if (!confirmed) return
  try {
    await api.deleteAiConversation(conversation.conversationId)
    conversationList.value = conversationList.value.filter((item) => item.conversationId !== conversation.conversationId)
    if (currentConversationId.value === conversation.conversationId) {
      setCurrentConversation('')
      chatTurns.value = []
    }
    showToast('会话已删除')
  } catch (error) {
    showToast(error.message || '删除会话失败')
  }
}

function setCurrentConversation(conversationId) {
  currentConversationId.value = conversationId || ''
  setAiConversationId(currentConversationId.value)
}

function messagesToChatTurns(messages) {
  const turns = []
  let pendingTurn = null
  for (const message of messages) {
    if (message.role === 'USER') {
      pendingTurn = {
        id: ++chatTurnId,
        userText: message.content,
        loading: false,
        error: '',
        response: null
      }
      turns.push(pendingTurn)
      continue
    }
    if (message.role !== 'ASSISTANT') continue
    if (!pendingTurn || pendingTurn.response || pendingTurn.error) {
      pendingTurn = {
        id: ++chatTurnId,
        userText: '继续上一次会话',
        loading: false,
        error: '',
        response: null
      }
      turns.push(pendingTurn)
    }
    if (message.status === 'FAILED') {
      pendingTurn.error = message.content
    } else {
      pendingTurn.response = normalizeAgentResponse({
        status: message.status,
        message: message.content,
        intent: message.intent,
        interrupted: message.status === 'WAITING_CONFIRMATION',
        agentState: message.agentState || {}
      })
    }
  }
  if (pendingTurn && !pendingTurn.response && !pendingTurn.error) {
    pendingTurn.error = '上次请求没有完成，可以重新尝试。'
  }
  return turns
}

function formatConversationTime(value) {
  if (!value) return '刚刚'
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

function normalizeAgentResponse(data) {
  const state = data?.agentState || {}
  const currentPlan = state.current_plan || state.plan_draft || null
  const dayCount = currentPlan?.days?.length || 0
  const destination = currentPlan?.destination
    || state.entities?.destination
    || state.tool_results?.weather?.data?.destination
    || '本次旅行'
  const selectedTools = Array.isArray(state.selected_tools) ? state.selected_tools : []
  const bookableCount = currentPlan ? countBookableItems(currentPlan, state.selected_options) : 0
  const budgetFeasibility = state.budget_feasibility || null
  const budgetBlocked = budgetFeasibility?.feasible === false
  const needsInput = state.next_action === 'ask_user' || Boolean(state.missing_fields?.length)
  const metrics = budgetBlocked
    ? [
        { label: '当前预算', value: formatAgentMoney(budgetFeasibility.budget_limit, budgetFeasibility.currency) },
        { label: '最低估算', value: formatAgentMoney(budgetFeasibility.estimated_minimum, budgetFeasibility.currency) },
        { label: '建议预算', value: formatAgentMoney(budgetFeasibility.suggested_budget, budgetFeasibility.currency) }
      ]
    : needsInput
    ? []
    : currentPlan
    ? [
        { label: '预计预算', value: formatAgentMoney(currentPlan.total_cost, currentPlan.currency) },
        { label: '行程天数', value: `${dayCount} 天` },
        { label: '待预订', value: `${bookableCount} 项` }
      ]
    : [
        { label: '调用工具', value: `${selectedTools.length} 项` },
        { label: '数据模式', value: agentDataMode(state) },
        { label: '会话消息', value: `${state.message_count || 0} 条` }
      ]

  return {
    status: data?.status || 'COMPLETED',
    intent: data?.intent || state.intent || 'unknown',
    interrupted: Boolean(data?.interrupted || state.interrupted),
    message: data?.message || 'Agent 已完成本次处理。',
    kicker: agentResultKicker(data, state, needsInput),
    title: agentResultTitle(data?.intent || state.intent, destination, dayCount, state, needsInput),
    metrics,
    tools: needsInput ? [] : selectedTools.map((tool) => agentToolLabel(tool)),
    plan: currentPlan,
    planPreview: buildPlanPreview(currentPlan),
    weatherSummary: state.tool_results?.weather?.data?.summary || '',
    selectedOptions: state.selected_options || {}
  }
}

function agentResultKicker(data, state, needsInput) {
  if (state.budget_feasibility?.feasible === false) return '预算需要调整'
  if (state.validation_exhausted) return '方案暂未保存'
  if (needsInput) return state.clarification_reply?.kicker || '再了解你一点'
  if (data?.interrupted || state.interrupted) return '等待你的确认'
  if (state.booking_completed) return '预订请求已提交'
  if (data?.intent === 'modify_plan') return '新版本已通过校验'
  if (state.plan_saved) return '方案已通过校验'
  return 'Agent 已完成'
}

function agentResultTitle(intent, destination, dayCount, state, needsInput) {
  if (state.budget_feasibility?.feasible === false) return `${destination}方案先调一下预算`
  if (state.validation_exhausted) return `${destination}行程需要调整`
  if (needsInput) return state.clarification_reply?.title || `${destination}已经记下啦`
  if (state.booking_completed) return '预订状态已更新'
  if (intent === 'booking') return '预订草稿已生成'
  if (intent === 'weather_query') return `${destination}天气查询`
  if (intent === 'hotel_query') return `${destination}住宿建议`
  if (intent === 'transport_query') return '城际交通方案'
  if (intent === 'modify_plan') return `${destination}行程已更新`
  if (intent === 'trip_plan' && dayCount > 0) return `${destination} ${dayCount} 天智能行程`
  if (intent === 'trip_plan') return `${destination}行程规划结果`
  return `${destination}旅行建议`
}

function agentToolLabel(tool) {
  const labels = {
    weather: '天气',
    hotel_search: '住宿区域',
    train_search: '火车',
    flight_search: '航班',
    poi_search: '景点候选',
    route_matrix: '路线矩阵',
    opening_hours: '开放时间',
    ticket: '门票'
  }
  return labels[tool] || tool
}

function agentDataMode(state) {
  const researchMode = state.phase2_research?.data_mode || state.phase1_research?.data_mode
  if (researchMode === 'AI_KNOWLEDGE') return 'AI 多阶段'
  if (researchMode === 'OFFLINE_FALLBACK') return '离线多阶段'
  const result = Object.values(state.tool_results || {}).find((item) => item?.data?.data_mode)
  if (!result) return 'AI 生成'
  return result?.data?.data_mode === 'MOCK' ? '接口演示' : (result?.data?.data_mode || 'AI 生成')
}

function countBookableItems(agentPlan, selectedOptions = {}) {
  if (!agentPlan) return 0
  return ['hotel_option_ids', 'transport_option_ids', 'ticket_option_ids']
    .reduce((total, key) => total + (Array.isArray(selectedOptions?.[key]) ? selectedOptions[key].length : 0), 0)
}

function formatAgentMoney(value, currency = 'CNY') {
  const amount = Number(value || 0).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
  return currency === 'CNY' ? `¥${amount}` : `${amount} ${currency}`
}

function buildPlanPreview(agentPlan) {
  if (!agentPlan?.days?.length) return []
  return agentPlan.days.slice(0, 2).map((day) => ({
    dayIndex: day.day_index,
    title: day.title || `第 ${day.day_index} 天`,
    items: (day.items || []).map((item) => item.name).join(' · ') || '自由活动'
  }))
}

function openAgentPlan(response) {
  if (!response.plan) return
  plan.value = convertAgentPlan(response.plan, response)
  selectedDayNo.value = 1
  go('trip')
}

function convertAgentPlan(agentPlan, response) {
  const days = agentPlan.days || []
  return {
    title: `${agentPlan.destination} ${days.length} 天智能行程`,
    days: days.length,
    peopleCount: planForm.peopleCount,
    totalBudget: Number(agentPlan.total_cost || 0),
    summary: agentPlan.assumptions?.join('；') || '',
    agentReason: [...new Set(days.map((day) => day.summary).filter(Boolean))].join('；'),
    weatherSummary: compactWeather(response.weatherSummary),
    bookableCount: countBookableItems(agentPlan, response.selectedOptions),
    dayPlans: days.map((day) => ({
      dayNo: day.day_index,
      date: day.date,
      title: day.date ? `Day ${day.day_index} · ${day.date}` : (day.title || `Day ${day.day_index}`),
      theme: (day.title || '').replace(/^第\s*\d+\s*天[：:]?\s*/, ''),
      summary: day.summary,
      items: (day.items || []).map((item) => ({
        itemType: item.item_type || 'SPOT',
        title: item.name,
        description: [item.description, item.travel_minutes ? `前往约 ${item.travel_minutes} 分钟` : ''].filter(Boolean).join('；'),
        startTime: (item.start_time || item.start_at || '').slice(0, 5),
        address: item.location_id || '位置待确认',
        duration: item.visit_minutes ? `约 ${item.visit_minutes} 分钟` : '时间待确认',
        durationMinutes: Number(item.visit_minutes || 0),
        travelMinutes: Number(item.travel_minutes || 0),
        bookable: Boolean(item.ticket_option_id),
        cost: Number(item.estimated_cost || 0)
      }))
    }))
  }
}

function compactWeather(summary) {
  const match = String(summary || '').match(/(\d+)\s*-\s*(\d+)\s*摄氏度/)
  return match ? `${match[1]}-${match[2]}°C` : (summary ? '天气已核对' : '天气待确认')
}

function itemDurationMinutes(item) {
  const structured = Number(item.durationMinutes || 0) + Number(item.travelMinutes || 0)
  if (structured) return structured
  const text = String(item.duration || '')
  const hourMatch = text.match(/([\d.]+)\s*小时/)
  const minuteMatch = text.match(/([\d.]+)\s*分钟/)
  return Number(hourMatch?.[1] || 0) * 60 + Number(minuteMatch?.[1] || 0)
}

function dayWeekday(day) {
  if (!day.date) return `第 ${day.dayNo} 天`
  return new Date(`${day.date}T00:00:00`).toLocaleDateString('zh-CN', { weekday: 'short' })
}

async function scrollChatToBottom() {
  await nextTick()
  if (chatListRef.value) {
    chatListRef.value.scrollTo({ top: chatListRef.value.scrollHeight, behavior: 'smooth' })
  }
}

function destinationStyle(city, index) {
  const images = {
    chengdu: '/oneclick-trip-assets/chengdu-destination.png',
    hangzhou: '/oneclick-trip-assets/hangzhou-west-lake.png',
    xian: '/oneclick-trip-assets/xian-city-wall.png',
    dali: '/oneclick-trip-assets/dali-erhai.png'
  }
  const positions = ['center 55%', 'center 30%', 'center 52%', 'center 18%']
  return {
    backgroundImage: "linear-gradient(180deg, rgba(17, 33, 28, 0.02), rgba(17, 33, 28, 0.72)), url('" + images[city.key] + "')",
    backgroundPosition: positions[index % positions.length]
  }
}

function itemIcon(type) {
  if (type === 'FOOD') return Food
  if (type === 'HOTEL') return OfficeBuilding
  if (type === 'TRANSPORT') return Van
  return Location
}

function itemTypeLabel(type) {
  if (type === 'FOOD') return '本地美食'
  if (type === 'HOTEL') return '住宿'
  if (type === 'TRANSPORT') return '交通'
  return '景点'
}

function isBookable(type) {
  return ['SPOT', 'FOOD', 'HOTEL', 'TRANSPORT'].includes(type)
}

function bookingLabel(type) {
  if (type === 'HOTEL') return '查看房型'
  if (type === 'FOOD') return '查看预约'
  if (type === 'TRANSPORT') return '查看车次'
  return '查看门票'
}

function bookingOffer(item) {
  if (item.itemType === 'HOTEL') return '舒适大床房 · ¥528 / 2 晚'
  if (item.itemType === 'FOOD') return '双人餐预约 · 到店付款'
  if (item.itemType === 'TRANSPORT') return '二等座 · ¥' + (item.cost || 20)
  return '成人票 · ¥' + (item.cost || 55)
}

function toggleBooking(title) {
  bookingItem.value = bookingItem.value === title ? '' : title
}

function confirmBooking(item) {
  bookingItem.value = ''
  showToast('已将“' + item.title + '”加入预订清单')
}

function dayTheme(dayNo) {
  if (Number(dayNo) === 2) return '熊猫、街区与火锅'
  if (Number(dayNo) === 3) return '都江堰慢游与返程'
  return '抵达成都，先感受市井'
}

function showToast(message) {
  clearTimeout(toastTimer)
  toastText.value = message
  toastTimer = setTimeout(() => {
    toastText.value = ''
  }, 2200)
}

function cityKeyByName(name) {
  if (name?.includes('杭州')) return 'hangzhou'
  if (name?.includes('西安')) return 'xian'
  if (name?.includes('大理')) return 'dali'
  return 'chengdu'
}

function summaryShortByName(name) {
  if (name?.includes('杭州')) return '湖边慢慢走'
  if (name?.includes('西安')) return '古都与碳水'
  if (name?.includes('大理')) return '吹风看洱海'
  return '美食与松弛感'
}
</script>
