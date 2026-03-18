<template>
  <div class="home-wrapper">
    <div class="home-header">
      <h2>知识图谱总览</h2>
      <div class="header-actions">
        <button class="refresh-btn" @click="refreshFullGraph">刷新全图</button>
      </div>
    </div>
    <div class="subgraph-query">
      <input v-model="diseaseName" @keyup.enter="fetchSubGraph" placeholder="请输入疾病名称" class="subgraph-input" />
      <button @click="fetchSubGraph" class="subgraph-btn">查询疾病子图</button>
      <span class="panel-hint">可输入疾病关键词查看关联的症状、治疗、科室等信息</span>
    </div>
    <div class="subgraph-query">
      <input v-model="symptom" @keyup.enter="fetchSubGraphBySymptom" placeholder="请输入症状名称" class="subgraph-input" />
      <button @click="fetchSubGraphBySymptom" class="subgraph-btn">查询症状子图</button>
      <span class="panel-hint">可输入症状关键词查看关联的疾病、治疗、科室等信息</span>
    </div>
    <div class="display-controls">
      <label class="control-item">
        <span>节点上限</span>
        <select v-model.number="maxNodes" @change="applyLimits" class="limit-select">
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
          <option :value="500">500</option>
        </select>
      </label>
      <label class="control-item">
        <span>关系上限</span>
        <select v-model.number="maxEdges" @change="applyLimits" class="limit-select">
          <option :value="50">50</option>
          <option :value="100">100</option>
          <option :value="200">200</option>
          <option :value="500">500</option>
        </select>
      </label>
    </div>
    <div class="filter-controls">
      <h4>节点筛选</h4>
      <div class="filter-options">
        <label v-for="type in availableNodeTypes" :key="type" class="filter-item">
          <input type="checkbox" :value="type" v-model="selectedNodeTypes" @change="applyNodeFilter" />
          {{ type }}
        </label>
      </div>
    </div>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="result" class="result-section">
      <h3>图谱关系可视化</h3>
      <div id="graph" class="graph-view"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'

const result = ref(null)
const loading = ref(false)
const error = ref('')
const diseaseName = ref('')
const symptom = ref('')
const maxNodes = ref(50)
const maxEdges = ref(50)
let chartInstance = null
let resizeHandler = null

const availableNodeTypes = ref([]); // 所有节点类型
const selectedNodeTypes = ref([]); // 用户选择的节点类型

onMounted(() => {
  // 确保页面加载完成后再调用 fetchFullGraph
  nextTick(() => {
    fetchFullGraph();
  });
});

function refreshFullGraph() {
  diseaseName.value = ''
  symptom.value = ''
  fetchFullGraph()
}

async function fetchFullGraph() {
  loading.value = true;
  error.value = '';
  try {
    const res = await fetch('/knowledge-graph/data', {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) throw new Error('无法获取知识图谱数据');
    const data = await res.json();
    if (data.code !== 200) throw new Error(data.msg || '获取知识图谱数据失败');
    result.value = data.data;

    // 确保容器渲染完成后再调用 drawGraph
    nextTick(() => {
      console.log('调用 drawGraph，result:', result.value);
      drawGraph(data.data);
    });
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function fetchSubGraph() {
  if (!diseaseName.value) {
    error.value = '请输入疾病名称'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const url = `/knowledge-graph/subgraph?disease=${encodeURIComponent(diseaseName.value)}&limit=${maxNodes.value}`
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json' }
    })
    if (!res.ok) throw new Error('子图请求失败：' + res.statusText)
    const data = await res.json()
    if (data.code !== 200) throw new Error(data.msg || '获取子图失败')
    result.value = data.data
    drawGraph(data.data)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function fetchSubGraphBySymptom() {
  if (!symptom.value) {
    error.value = '请输入症状名称';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    const url = `/knowledge-graph/subgraph-by-symptom?symptom=${encodeURIComponent(symptom.value)}&limit=${maxNodes.value}`;
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) throw new Error('子图请求失败：' + res.statusText);
    const data = await res.json();
    if (data.code !== 200) throw new Error(data.msg || '获取子图失败');

    console.log('后端返回数据:', data.data); // 调试日志

    result.value = data.data;
    drawGraph(data.data);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function drawGraph(data) {
  const dom = document.getElementById('graph');
  if (!dom) {
    console.error('图表容器未找到，请检查是否正确渲染了 id="graph" 的 DOM 元素');
    console.log('当前 result 值:', result.value);
    return;
  }

  console.log('绘图数据:', data);
  if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) {
    console.error('数据格式错误，无法绘制图表');
    return;
  }

  const existed = echarts.getInstanceByDom(dom);
  if (existed) {
    console.log('销毁旧的 ECharts 实例');
    existed.dispose();
  }

  const myChart = echarts.init(dom);
  chartInstance = myChart;

  const typeColorMap = {
    '疾病': '#4f46e5',
    '症状': '#3b82f6',
    '科室': '#ec4899',
    '诊断方法': '#14b8a6',
    '治疗': '#7c3aed',
    '病因': '#0ea5e9',
    '其他': '#94a3b8'
  };
  const fallbackPalette = [
    '#2563eb', '#1d4ed8', '#0ea5e9', '#38bdf8', '#6366f1', '#7c3aed', '#8b5cf6', '#a78bfa', '#d946ef', '#ec4899', '#f43f5e', '#ef4444', '#f97316', '#f59e0b', '#10b981', '#14b8a6', '#06b6d4', '#94a3b8'
  ];

  let nodes = [];
  let links = [];
  let categoryNames = [];
  const catIndex = new Map();

  if (Array.isArray(data?.nodes) && Array.isArray(data?.edges)) {
    const originalNodes = data.nodes;
    const selectedNodes = originalNodes.slice(0, Math.max(0, maxNodes.value || 0));
    const idSet = new Set(selectedNodes.map(n => String(n.id ?? '')));
    const nameSet = new Set(selectedNodes.map(n => String(n.name ?? n.properties?.name ?? n.properties?.label ?? n.label ?? '')));

    const filteredEdges = data.edges.filter(l => {
      const s = String(l.source);
      const t = String(l.target);
      const sIn = (s && (idSet.has(s) || nameSet.has(s)));
      const tIn = (t && (idSet.has(t) || nameSet.has(t)));
      return sIn && tIn;
    }).slice(0, Math.max(0, maxEdges.value || 0));

    selectedNodes.forEach(n => {
      const type = (n.label || n.type || n.properties?.type || n.properties?.labels?.[0] || '其他') + '';
      if (!catIndex.has(type)) {
        catIndex.set(type, categoryNames.length);
        categoryNames.push(type);
      }
    });

    nodes = selectedNodes.map(n => {
      const type = (n.label || n.type || n.properties?.type || n.properties?.labels?.[0] || '其他') + '';
      const idx = catIndex.get(type) ?? 0;
      const name = n.name || n.properties?.name || n.properties?.label || n.properties?.title || n.properties?.desc || n.label || String(n.id);
      return {
        ...n,
        name,
        symbolSize: n.symbolSize || 48,
        category: idx,
        label: { show: true, fontWeight: 'bold', color: '#111827', fontSize: 12, distance: 6 }
      };
    });

    links = filteredEdges.map(l => ({
      ...l,
      lineStyle: { color: '#cbd5e1', width: 1.5 },
      label: l.label ? { show: true, formatter: l.label, color: '#334155', fontSize: 11 } : undefined
    }));
  }

  const categories = categoryNames.map((name, i) => ({
    name,
    itemStyle: { color: typeColorMap[name] || fallbackPalette[i % fallbackPalette.length] }
  }));

  myChart.setOption({
    backgroundColor: '#ffffff',
    tooltip: {
      show: true,
      formatter: params => {
        if (params.dataType === 'edge') {
          return params.data?.label?.formatter || params.data?.value || '';
        }
        return params.data?.name || '';
      }
    },
    legend: [{ data: categories.map(c => c.name), top: 30, textStyle: { color: '#334155' } }],
    series: [{
      type: 'graph',
      layout: 'force',
      data: nodes,
      links: links,
      categories: categories,
      roam: true,
      draggable: true,
      label: { show: true, position: 'right', fontWeight: 'bold', color: '#111827' },
      force: { repulsion: 480, edgeLength: 150, friction: 0.2 },
      edgeSymbol: ['circle', 'arrow'],
      edgeSymbolSize: [6, 14],
      lineStyle: { color: '#cbd5e1', width: 1.5, curveness: 0.08 },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3, color: '#2563eb' },
        itemStyle: { borderColor: '#3b82f6', borderWidth: 2 }
      }
    }]
  });

  if (!resizeHandler) {
    resizeHandler = () => {
      if (chartInstance) chartInstance.resize();
    };
    window.addEventListener('resize', resizeHandler);
  }
}

watch(result, (val) => {
  if (val) {
    // 提取所有节点类型
    const types = new Set(val.nodes.map(node => node.label || '其他'));
    availableNodeTypes.value = Array.from(types);
    selectedNodeTypes.value = availableNodeTypes.value; // 默认全选
    drawGraph(val);
  }
})

function applyLimits() {
  if (result.value) drawGraph(result.value)
}

function applyNodeFilter() {
  if (!result.value) return;

  const filteredNodes = result.value.nodes.filter(node => selectedNodeTypes.value.includes(node.label || '其他'));
  const filteredNodeIds = new Set(filteredNodes.map(node => node.id));

  const filteredEdges = result.value.edges.filter(edge =>
    filteredNodeIds.has(edge.source) && filteredNodeIds.has(edge.target)
  );

  drawGraph({ nodes: filteredNodes, edges: filteredEdges });
}

onBeforeUnmount(() => {
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
    resizeHandler = null
  }
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
})
</script>

<style scoped>
.home-wrapper {
  padding: 32px 40px;
  background: #f8fafc; /* slate-50 */
  min-height: 100vh;
}
.home-header {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.home-header h2 {
  color: #0f172a; /* slate-900 */
  font-size: 2rem;
  margin-bottom: 16px;
}
.header-actions { display: flex; gap: 12px; }
.refresh-btn {
  padding: 10px 16px;
  border: 1px solid #e2e8f0; /* slate-200 */
  background: #ffffff;
  color: #0f172a;
  border-radius: 10px;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.refresh-btn:hover {
  border-color: #cbd5e1; /* slate-300 */
  box-shadow: 0 2px 6px rgba(2,6,23,0.08);
}
.display-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 8px 0 16px 0;
}
.control-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #334155; /* slate-700 */
}
.limit-select {
  padding: 8px 10px;
  border: 1px solid #e2e8f0; /* slate-200 */
  border-radius: 8px;
  background: #fff;
  color: #0f172a;
}
.limit-select:focus {
  outline: none;
  border-color: #93c5fd; /* blue-300 */
  box-shadow: 0 0 0 2px #dbeafe; /* blue-100 */
}
.subgraph-query {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.subgraph-input {
  padding: 10px 12px;
  border: 1px solid #e2e8f0; /* slate-200 */
  border-radius: 8px;
  background: #fff;
  color: #0f172a;
  min-width: 260px;
}
.subgraph-input:focus {
  outline: none;
  border-color: #93c5fd; /* blue-300 */
  box-shadow: 0 0 0 2px #dbeafe; /* blue-100 */
}
.subgraph-btn {
  padding: 10px 16px;
  border: none;
  border-radius: 8px;
  background: #3b82f6; /* blue-500 */
  color: #ffffff;
  cursor: pointer;
}
.subgraph-btn:hover {
  background: #2563eb; /* blue-600 */
}
.panel-hint {
  color: #64748b; /* slate-500 */
}
.loading {
  color: #0ea5e9; /* sky-500 */
  margin: 18px 0;
}
.error {
  color: #e74c3c;
  margin: 18px 0;
}
.result-section {
  margin-top: 24px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(2, 6, 23, 0.06);
  padding: 24px;
}
.result-section h3 {
  color: #0f172a;
  margin-bottom: 12px;
}
.graph-view {
  width: 100%;
  min-width: 400px;
  height: 72vh; /* 放大画布以便更多节点显示 */
  min-height: 480px;
  margin-top: 20px;
}
.filter-controls {
  margin: 16px 0;
  padding: 12px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
.filter-controls h4 {
  margin-bottom: 8px;
  color: #0f172a;
  font-size: 1.1rem;
}
.filter-options {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}
.filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.9rem;
  color: #334155;
}
</style>
