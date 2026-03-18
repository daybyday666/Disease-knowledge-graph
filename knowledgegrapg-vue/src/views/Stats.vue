<template>
  <div class="stats-bg">
    <div class="stats-wrapper glass-card">
      <h2>知识图谱统计信息</h2>
      <div v-if="loading" class="loading">加载中...</div>
      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="stats" class="charts-flex">
        <div class="chart-container glass-inner">
          <div id="pie-chart" class="chart"></div>
        </div>
        <div class="chart-container glass-inner">
          <div id="bar-chart" class="chart"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue';
import * as echarts from 'echarts';

const stats = ref(null);
const loading = ref(false);
const error = ref('');
let pieInstance = null;
let barInstance = null;

const colorPalette = [
  '#ff6b81', // 粉红
  '#feca57', // 橙黄
  '#48dbfb', // 天蓝
  '#1dd1a1', // 绿松
  '#5f27cd', // 紫
  '#ff9ff3'  // 亮粉
];

onMounted(() => {
  fetchStats();
});

async function fetchStats() {
  loading.value = true;
  error.value = '';
  try {
    const res = await fetch('/knowledge-graph/stats', {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) throw new Error(`HTTP 错误: ${res.status} ${res.statusText}`);
    const data = await res.json();
    if (data.code !== 200) throw new Error(data.msg || '获取统计信息失败');
    stats.value = {
      diseaseCount: data.data.diseaseCount || 0,
      symptomCount: data.data.symptomCount || 0,
      diagnosisCount: data.data.drugCount || 0, // 诊断方法
      departmentCount: data.data.keshi || 0, // 科室
      treatmentCount: data.data.treatment || 0, // 治疗
      reasonCount: data.data.reason || 0 // 病因
    };
    nextTick(() => {
      drawPieChart();
      drawBarChart();
    });
  } catch (e) {
    console.error('获取统计信息失败:', e);
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function drawPieChart() {
  const chartDom = document.getElementById('pie-chart');
  if (!chartDom) return;
  if (pieInstance) pieInstance.dispose();
  pieInstance = echarts.init(chartDom);
  const pieData = [
    { value: stats.value.diseaseCount, name: '疾病' },
    { value: stats.value.symptomCount, name: '症状' },
    { value: stats.value.diagnosisCount, name: '诊断方法' },
    { value: stats.value.departmentCount, name: '科室' },
    { value: stats.value.treatmentCount, name: '治疗' },
    { value: stats.value.reasonCount, name: '病因' }
  ];
  pieInstance.setOption({
    color: colorPalette,
    title: {
      text: '实体类型分布',
      left: 'center',
      top: 10,
      textStyle: { color: '#0f172a', fontSize: 16 }
    },
    tooltip: {
      trigger: 'item',
      formatter: '{b}: {c} ({d}%)'
    },
    legend: {
      orient: 'vertical',
      left: 'left',
      top: 40,
      textStyle: { color: '#334155', fontWeight: 'bold' }
    },
    series: [
      {
        name: '实体类型',
        type: 'pie',
        radius: ['35%', '65%'],
        center: ['55%', '55%'],
        avoidLabelOverlap: false,
        label: {
          show: false
        },
        emphasis: {
          label: {
            show: true,
            fontSize: 16,
            fontWeight: 'bold',
            color: '#222'
          }
        },
        labelLine: { show: false },
        data: pieData
      }
    ]
  });
}

function drawBarChart() {
  const chartDom = document.getElementById('bar-chart');
  if (!chartDom) return;
  if (barInstance) barInstance.dispose();
  barInstance = echarts.init(chartDom);
  const barData = [
    stats.value.diseaseCount,
    stats.value.symptomCount,
    stats.value.diagnosisCount,
    stats.value.departmentCount,
    stats.value.treatmentCount,
    stats.value.reasonCount
  ];
  barInstance.setOption({
    color: ['#48dbfb'],
    title: {
      text: '实体数量对比',
      left: 'center',
      top: 10,
      textStyle: { color: '#0f172a', fontSize: 16 }
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' }
    },
    grid: {
      left: '8%',
      right: '8%',
      bottom: '12%',
      top: 60,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      data: ['疾病', '症状', '诊断方法', '科室', '治疗', '病因'],
      axisLabel: { color: '#334155', fontWeight: 'bold', fontSize: 14 }
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#334155', fontWeight: 'bold', fontSize: 14 }
    },
    series: [
      {
        data: barData,
        type: 'bar',
        barWidth: '45%',
        itemStyle: {
          borderRadius: [8, 8, 0, 0],
          shadowColor: '#48dbfb',
          shadowBlur: 10
        },
        label: {
          show: true,
          position: 'top',
          color: '#ff6b81',
          fontWeight: 'bold',
          fontSize: 14
        }
      }
    ]
  });
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');

.stats-bg {
  min-height: 100vh;
  width: 100vw;
  background: linear-gradient(120deg, #e0e7ff 0%, #f8fafc 60%, #f0abfc 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
}
.stats-wrapper {
  padding: 40px 48px 48px 48px;
  min-width: 340px;
  max-width: 1100px;
  width: 98vw;
  min-height: 70vh;
  border-radius: 32px;
  box-shadow: 0 8px 40px 0 rgba(80, 80, 180, 0.13), 0 1.5px 8px rgba(16,185,129,0.06);
  margin: 48px auto;
  backdrop-filter: blur(18px) saturate(1.2);
  background: rgba(255,255,255,0.55);
  border: 1.5px solid rgba(180,180,255,0.18);
  transition: box-shadow 0.3s, background 0.3s;
}
.glass-card {
  box-shadow: 0 8px 40px 0 rgba(80, 80, 180, 0.13), 0 1.5px 8px rgba(16,185,129,0.06);
  background: rgba(255,255,255,0.55);
  backdrop-filter: blur(18px) saturate(1.2);
  border-radius: 32px;
  border: 1.5px solid rgba(180,180,255,0.18);
}
.glass-inner {
  background: rgba(255,255,255,0.75);
  box-shadow: 0 4px 24px rgba(80, 80, 180, 0.10);
  border-radius: 24px;
  border: 1px solid rgba(180,180,255,0.10);
  transition: box-shadow 0.2s, background 0.2s;
}
.stats-wrapper h2 {
  color: #3b82f6;
  font-size: 2.4rem;
  margin-bottom: 28px;
  text-align: center;
  font-weight: 800;
  letter-spacing: 2px;
  text-shadow: 0 2px 12px #e0e7ff;
  background: linear-gradient(90deg, #6366f1 10%, #f472b6 90%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.charts-flex {
  display: flex;
  flex-wrap: wrap;
  gap: 40px;
  justify-content: center;
  align-items: flex-start;
  margin-top: 32px;
}
.chart-container {
  flex: 1 1 380px;
  min-width: 340px;
  max-width: 480px;
  height: 420px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: box-shadow 0.2s, background 0.2s;
  box-shadow: 0 2px 16px rgba(99,102,241,0.10);
  margin-bottom: 12px;
  position: relative;
  overflow: hidden;
}
.chart-container:hover {
  box-shadow: 0 8px 32px rgba(99,102,241,0.18);
  background: rgba(255,255,255,0.92);
}
.chart {
  width: 97%;
  height: 92%;
  z-index: 2;
}
.loading {
  color: #6366f1;
  margin: 28px 0 18px 0;
  text-align: center;
  font-size: 1.2rem;
  font-weight: 600;
  letter-spacing: 1px;
  animation: fadeIn 1.2s;
}
.error {
  color: #e74c3c;
  margin: 18px 0;
  text-align: center;
  font-size: 1.1rem;
  font-weight: 600;
  background: rgba(255, 228, 230, 0.7);
  border-radius: 12px;
  padding: 10px 0;
  animation: shake 0.4s;
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
@keyframes shake {
  0% { transform: translateX(0); }
  20% { transform: translateX(-6px); }
  40% { transform: translateX(6px); }
  60% { transform: translateX(-4px); }
  80% { transform: translateX(4px); }
  100% { transform: translateX(0); }
}
@media (max-width: 980px) {
  .stats-wrapper {
    padding: 18px 2vw 32px 2vw;
    min-width: unset;
    max-width: 100vw;
    border-radius: 18px;
  }
  .charts-flex {
    flex-direction: column;
    gap: 24px;
  }
  .chart-container {
    min-width: 90vw;
    max-width: 100vw;
    height: 320px;
    border-radius: 16px;
  }
}
</style>