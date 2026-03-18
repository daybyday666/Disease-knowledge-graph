<template>
  <div class="app-layout">
    <Header />
    <div class="main-content">
      <Menu />
      <div class="view-content">
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup>
import Header from './layout/header/index.vue'
import Menu from './layout/menu/index.vue'
</script>

<style scoped>
.app-layout {
  min-height: 100vh;
  background: #ffffff;
  display: flex;
  flex-direction: column;
}
.main-content {
  display: flex;
  flex: 1;
  min-height: 0;
}
.view-content {
  flex: 1;
  padding: 32px 40px;
  background: #ffffff;
  min-height: calc(100vh - 60px);
  overflow: auto;
}
</style>
