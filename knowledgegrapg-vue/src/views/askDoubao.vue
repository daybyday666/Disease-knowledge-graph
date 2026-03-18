<template>
  <div class="chat-bg">
    <div class="chat-container">
      <div class="chat-header">
        <span class="chat-title">🤖 智能问答助手</span>
      </div>
      <div class="chat-recommend">
        <span class="rec-title">推荐提问：</span>
        <div class="rec-list">
          <button v-for="rec in recommendQuestions" :key="rec" class="rec-btn" @click="fillRecommend(rec)">{{ rec }}</button>
        </div>
      </div>
      <div class="chat-history" ref="chatHistoryRef">
        <div v-for="msg in chatList" :key="msg.id" :class="['chat-msg', msg.role]">
          <div class="avatar">{{ msg.role === 'user' ? '🧑' : '🤖' }}</div>
          <div class="bubble">
            <div v-if="msg.role === 'user'" class="bubble-user">{{ msg.content }}</div>
            <div v-else class="bubble-bot">
              <span v-if="msg.loading" class="loading-dot">...</span>
              <span v-else>{{ msg.content }}</span>
            </div>
          </div>
        </div>
      </div>
      <form class="chat-input-bar" @submit.prevent="handleSubmit">
        <input
          v-model="question"
          class="chat-input"
          :placeholder="inputPlaceholder"
          autocomplete="off"
          :disabled="loading"
          @keydown.enter.exact.prevent="handleSubmit"
        />
        <button type="submit" class="chat-send-btn" :disabled="loading || !question.trim()">
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          <span v-else>发送</span>
        </button>
      </form>
      <div v-if="error" class="chat-error">{{ error }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'

const question = ref('')
const error = ref('')
const loading = ref(false)
const chatList = ref<{ id: number; role: 'user' | 'bot'; content: string; loading?: boolean }[]>([])
const chatHistoryRef = ref<HTMLElement | null>(null)
const inputPlaceholder = '请输入您的问题...'

const recommendQuestions: string[] = [
  '感冒的常见症状和治疗方法？',
  '高血压有哪些危害？',
  '如何预防糖尿病？',
  '头痛可能是什么原因？',
  '儿童发烧怎么办？',
  '新冠和流感的区别？'
]

function fillRecommend(q: string) {
  question.value = q
}

function scrollToBottom() {
  nextTick(() => {
    if (chatHistoryRef.value) {
      chatHistoryRef.value.scrollTop = chatHistoryRef.value.scrollHeight
    }
  })
}

const handleSubmit = async () => {
  if (!question.value.trim()) {
    error.value = '请输入问题！'
    return
  }
  error.value = ''
  loading.value = true
  const userMsg = {
    id: Date.now() + Math.random(),
    role: 'user' as const,
    content: question.value.trim()
  }
  chatList.value.push(userMsg)
  const botMsg = {
    id: Date.now() + Math.random(),
    role: 'bot' as const,
    content: '',
    loading: true
  }
  chatList.value.push(botMsg)
  scrollToBottom()
  try {
    const res = await fetch('/knowledge-graph/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ question: userMsg.content })
    })
    const data = await res.json()
    if (data.code === 200) {
      botMsg.content = data.data
    } else {
      botMsg.content = data.msg || '获取建议失败'
    }
  } catch (e) {
    botMsg.content = '请求失败，请重试。'
  } finally {
    botMsg.loading = false
    loading.value = false
    question.value = ''
    scrollToBottom()
  }
}

onMounted(scrollToBottom)
</script>

<style scoped>
  .chat-bg {
    background: linear-gradient(120deg, #eef2ff 0%, #f8fafc 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
  }
  .chat-container {
    width: 100%;
    max-width: 640px;
    background: rgba(255,255,255,0.9);
    border-radius: 20px;
    box-shadow: 0 8px 28px rgba(2, 6, 23, 0.10);
    padding: 0 0 18px 0;
    display: flex;
    flex-direction: column;
    min-height: 70vh;
    margin: 32px 12px;
  }
  .chat-header {
    padding: 22px 24px 10px 24px;
    border-radius: 20px 20px 0 0;
    background: linear-gradient(90deg, #6366f1 10%, #a78bfa 90%);
    color: #fff;
    font-size: 1.2rem;
    font-weight: 800;
    letter-spacing: 1px;
    text-align: left;
    box-shadow: 0 2px 8px rgba(99,102,241,0.10);
  }
  .chat-title {
    background: linear-gradient(90deg, #fff 10%, #f472b6 90%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .chat-recommend {
    padding: 12px 20px 0 20px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .rec-title {
    color: #6366f1;
    font-weight: 600;
    font-size: 0.95rem;
    margin-bottom: 4px;
  }
  .rec-list { display: flex; flex-wrap: wrap; gap: 8px; }
  .rec-btn {
    background: linear-gradient(90deg, #a5b4fc 10%, #f0abfc 90%);
    color: #3b0764;
    border: none;
    border-radius: 16px;
    padding: 6px 14px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.18s, color 0.18s, box-shadow 0.18s;
    box-shadow: 0 1px 4px #e0e7ff;
  }
  .rec-btn:hover { background: linear-gradient(90deg, #6366f1 10%, #f472b6 90%); color: #fff; }
  .chat-history {
    flex: 1 1 auto;
    overflow-y: auto;
    padding: 14px 16px 8px 16px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    min-height: 320px;
    max-height: 55vh;
    scroll-behavior: smooth;
  }
  .chat-msg { display: flex; align-items: flex-end; gap: 10px; animation: fadeIn 0.3s; }
  .chat-msg.user { flex-direction: row-reverse; }
  .chat-msg .avatar {
    width: 34px; height: 34px; border-radius: 50%;
    background: linear-gradient(135deg, #a5b4fc 10%, #f0abfc 90%);
    color: #fff; display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem; font-weight: 700; box-shadow: 0 1px 6px #e0e7ff;
  }
  .chat-msg.user .avatar { background: linear-gradient(135deg, #6366f1 10%, #f472b6 90%); }
  .bubble { max-width: 78%; display: flex; flex-direction: column; }
  .bubble-user {
    background: linear-gradient(90deg, #6366f1 10%, #a78bfa 90%);
    color: #fff; border-radius: 14px 14px 4px 14px;
    padding: 10px 14px; font-size: 1rem; font-weight: 500;
    box-shadow: 0 2px 8px #e0e7ff; word-break: break-word;
  }
  .bubble-bot {
    background: #f3f4f6; color: #111827; border-radius: 14px 14px 14px 4px;
    padding: 10px 14px; font-size: 1rem; font-weight: 500;
    box-shadow: 0 2px 8px #e0e7ff; word-break: break-word;
  }
  .loading-dot { color: #6366f1; font-size: 1.1rem; letter-spacing: 2px; animation: blink 1s infinite; }
  @keyframes blink { 0%,100%{opacity:1;} 50%{opacity:0.3;} }
  .chat-input-bar { display: flex; align-items: center; gap: 10px; padding: 0 16px; margin-top: 8px; }
  .chat-input {
    flex: 1; padding: 12px 14px; border-radius: 14px; border: 1.5px solid #e0e8f0;
    font-size: 1rem; background: #fff; color: #0f172a; transition: border 0.2s, box-shadow 0.2s; outline: none;
  }
  .chat-input:focus { border-color: #a78bfa; box-shadow: 0 0 0 2px #dbeafe; }
  .chat-send-btn {
    padding: 11px 18px; border-radius: 14px; border: none;
    background: linear-gradient(90deg, #6366f1 10%, #f472b6 90%);
    color: #fff; font-weight: 700; font-size: 1rem; cursor: pointer;
    transition: background 0.2s, box-shadow 0.2s; box-shadow: 0 2px 8px #e0e7ff;
    display: inline-flex; align-items: center; gap: 8px;
  }
  .chat-send-btn:disabled { background: #c7d2fe; color: #fff; cursor: not-allowed; }
  .spinner { width: 16px; height: 16px; border-radius: 50%; border: 2px solid #dbeafe; border-top-color: #a78bfa; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .chat-error { color: #b91c1c; background: #fee2e2; border-radius: 10px; padding: 10px 16px; margin: 12px 16px 0 16px; text-align: left; font-size: 0.95rem; font-weight: 600; animation: shake 0.4s; }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  @keyframes shake { 0%{transform:translateX(0);}20%{transform:translateX(-6px);}40%{transform:translateX(6px);}60%{transform:translateX(-4px);}80%{transform:translateX(4px);}100%{transform:translateX(0);} }
  @media (max-width: 700px) {
    .chat-container { max-width: 100vw; margin: 0; border-radius: 0; min-height: 100vh; }
    .chat-history { max-height: calc(100vh - 220px); }
  }
  </style>