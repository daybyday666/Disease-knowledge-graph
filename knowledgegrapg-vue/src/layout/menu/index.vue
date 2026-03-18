<template>
  <aside :class="['sidebar', { collapsed }]">
    <div class="brand" @click="toggle" role="button" tabindex="0" aria-label="切换侧边栏" @keyup.enter="toggle">>
      <span class="title" v-if="!collapsed">知识图谱系统</span>
      <span class="collapse-tip" v-else>展开</span>
    </div>
    <nav class="nav">
      <router-link to="/" class="nav-item" active-class="active" aria-label="首页-知识图谱">
        <span class="text" v-if="!collapsed">知识图谱</span>
      </router-link>
      <router-link to="/ask" class="nav-item" active-class="active" aria-label="AI问答">
        <span class="text" v-if="!collapsed">AI 问答</span>
      </router-link>
      <router-link to="/stats" class="nav-item" active-class="active" aria-label="知识图谱统计">
        <span class="text" v-if="!collapsed">知识图谱统计</span>
      </router-link>
      <router-link to="/forum" class="nav-item" active-class="active" aria-label="论坛交流">
        <span class="text" v-if="!collapsed">论坛交流</span>
      </router-link>
    </nav>
  </aside>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const collapsed = ref(false)

onMounted(() => {
  const saved = localStorage.getItem('sidebar-collapsed')
  collapsed.value = saved === '1'
})

function toggle() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar-collapsed', collapsed.value ? '1' : '0')
}
</script>

<style scoped>
.sidebar {
  width: 220px;
  height: 100vh;
  background: #ffffff;
  border-right: 1px solid #eef0f5;
  box-shadow: 0 2px 12px rgba(17, 24, 39, 0.04);
  display: flex;
  flex-direction: column;
  position: sticky;
  top: 0;
}
.sidebar.collapsed {
  width: 72px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 60px;
  padding: 0 16px;
  border-bottom: 1px solid #f2f3f7;
  cursor: pointer;
}
.logo {
  font-size: 20px;
}
.title {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}
.collapse-tip {
  font-size: 12px;
  color: #6b7280;
}
.nav {
  padding: 12px 8px;
  display: grid;
  gap: 8px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  color: #374151;
  text-decoration: none;
  transition: background 0.15s, color 0.15s, transform 0.15s;
}
.nav-item .icon {
  width: 20px;
  text-align: center;
}
.nav-item:hover {
  background: #f1f5f9; /* slate-100 */
  color: #0f172a;
  transform: translateY(-1px);
}
.nav-item.active {
  background: #eff6ff; /* blue-50 */
  color: #1d4ed8; /* blue-700 */
  box-shadow: inset 0 0 0 1px #bfdbfe; /* blue-200 */
}
.nav :is(.router-link-active, .router-link-exact-active) {
  background: #eff6ff; /* blue-50 */
  color: #1d4ed8; /* blue-700 */
  box-shadow: inset 0 0 0 1px #bfdbfe; /* blue-200 */
}
.nav-item:focus {
  outline: none;
  box-shadow: 0 0 0 2px #dbeafe; /* blue-100 */
}
.brand:focus {
  outline: none;
  box-shadow: inset 0 0 0 2px #dbeafe; /* blue-100 */
}
</style>