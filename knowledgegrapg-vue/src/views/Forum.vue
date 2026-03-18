<template>
  <div class="forum-wrapper">
    <h2>疾病知识交流区</h2>
    <div class="forum-main">
      <div class="forum-post-form">
        <textarea v-model="newPostContent" placeholder="发表你的问题、经验或见解..." rows="3"></textarea>
        <button @click="submitPost" :disabled="!newPostContent.trim()">发布</button>
      </div>
      <div class="forum-list">
        <div v-if="posts.length === 0" class="forum-empty">暂无帖子，快来发表第一个话题吧！</div>
        <div v-for="post in posts" :key="post.id" class="forum-post">
          <div class="post-header">
            <span class="post-user">{{ post.user }}</span>
            <span class="post-time">{{ formatTime(post.time) }}</span>
          </div>
          <div class="post-content">{{ post.content }}</div>
          <div class="post-actions">
            <button @click="toggleReply(post.id)">回复</button>
          </div>
          <div v-if="replyingId === post.id" class="reply-form">
            <textarea v-model="replyContent" placeholder="写下你的回复..." rows="2"></textarea>
            <button @click="submitReply(post.id)" :disabled="!replyContent.trim()">回复</button>
            <button class="cancel-btn" @click="cancelReply">取消</button>
          </div>
          <div v-if="post.replies && post.replies.length" class="replies">
            <div v-for="reply in post.replies" :key="reply.id" class="reply-item">
              <span class="reply-user">{{ reply.user }}</span>：
              <span class="reply-content">{{ reply.content }}</span>
              <span class="reply-time">{{ formatTime(reply.time) }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const posts = ref([])
const newPostContent = ref('')
const replyingId = ref(null)
const replyContent = ref('')

function submitPost() {
  if (!newPostContent.value.trim()) return
  posts.value.unshift({
    id: Date.now() + Math.random(),
    user: '匿名用户',
    content: newPostContent.value,
    time: Date.now(),
    replies: []
  })
  newPostContent.value = ''
}

function toggleReply(postId) {
  if (replyingId.value === postId) {
    replyingId.value = null
    replyContent.value = ''
  } else {
    replyingId.value = postId
    replyContent.value = ''
  }
}

function cancelReply() {
  replyingId.value = null
  replyContent.value = ''
}

function submitReply(postId) {
  if (!replyContent.value.trim()) return
  const post = posts.value.find(p => p.id === postId)
  if (post) {
    post.replies = post.replies || []
    post.replies.push({
      id: Date.now() + Math.random(),
      user: '匿名回复',
      content: replyContent.value,
      time: Date.now()
    })
  }
  replyingId.value = null
  replyContent.value = ''
}

function formatTime(ts) {
  const d = new Date(ts)
  return d.toLocaleString()
}
</script>

<style scoped>
.forum-wrapper {
  padding: 32px 40px;
  background: linear-gradient(120deg, #f8fafc 60%, #e0e7ff 100%);
  min-height: 100vh;
}
.forum-wrapper h2 {
  color: #3b82f6;
  font-size: 2.2rem;
  margin-bottom: 28px;
  text-align: center;
  letter-spacing: 2px;
  font-weight: 800;
  text-shadow: 0 2px 8px #e0e7ff;
}
.forum-main {
  max-width: 820px;
  margin: 0 auto;
  background: #fff;
  border-radius: 18px;
  box-shadow: 0 4px 24px rgba(59,130,246,0.08), 0 1.5px 8px rgba(16,185,129,0.06);
  padding: 40px 32px 32px 32px;
}
.forum-post-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 38px;
}
.forum-post-form textarea {
  resize: vertical;
  border: 1.5px solid #a5b4fc;
  border-radius: 10px;
  padding: 14px;
  font-size: 1.08rem;
  color: #334155;
  background: #f1f5ff;
  transition: border 0.2s;
}
.forum-post-form textarea:focus {
  border-color: #3b82f6;
  outline: none;
  box-shadow: 0 0 0 2px #bae6fd;
}
.forum-post-form button {
  align-self: flex-end;
  padding: 10px 32px;
  background: linear-gradient(90deg, #3b82f6 60%, #38bdf8 100%);
  color: #fff;
  border: none;
  border-radius: 10px;
  font-weight: bold;
  font-size: 1.08em;
  cursor: pointer;
  transition: background 0.2s, box-shadow 0.2s;
  box-shadow: 0 2px 8px #bae6fd;
}
.forum-post-form button:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
  box-shadow: none;
}
.forum-list {
  display: flex;
  flex-direction: column;
  gap: 28px;
}
.forum-empty {
  color: #64748b;
  text-align: center;
  margin: 36px 0;
  font-size: 1.1em;
}
.forum-post {
  background: linear-gradient(90deg, #f1f5f9 80%, #e0e7ff 100%);
  border-radius: 12px;
  padding: 22px 18px 14px 18px;
  box-shadow: 0 2px 8px rgba(59,130,246,0.06);
  border-left: 5px solid #3b82f6;
  position: relative;
  transition: box-shadow 0.2s;
}
.forum-post:hover {
  box-shadow: 0 6px 24px rgba(59,130,246,0.13);
}
.post-header {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 10px;
}
.post-user {
  color: #2563eb;
  font-weight: bold;
  font-size: 1.08em;
}
.post-time {
  color: #94a3b8;
  font-size: 0.98em;
}
.post-content {
  color: #0f172a;
  font-size: 1.13em;
  margin-bottom: 12px;
  white-space: pre-wrap;
  line-height: 1.7;
}
.post-actions {
  margin-bottom: 10px;
}
.post-actions button {
  background: none;
  border: none;
  color: #3b82f6;
  cursor: pointer;
  font-size: 1em;
  padding: 0 10px 0 0;
  font-weight: 600;
  transition: color 0.15s;
}
.post-actions button:hover {
  color: #2563eb;
}
.reply-form {
  margin: 10px 0 0 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.reply-form textarea {
  resize: vertical;
  border: 1.5px solid #a5b4fc;
  border-radius: 8px;
  padding: 10px;
  font-size: 1em;
  color: #334155;
  background: #f1f5ff;
  transition: border 0.2s;
}
.reply-form textarea:focus {
  border-color: #38bdf8;
  outline: none;
  box-shadow: 0 0 0 2px #bae6fd;
}
.reply-form button {
  align-self: flex-start;
  padding: 7px 22px;
  background: linear-gradient(90deg, #10b981 60%, #38bdf8 100%);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-weight: bold;
  font-size: 1em;
  cursor: pointer;
  margin-right: 10px;
  transition: background 0.2s, box-shadow 0.2s;
  box-shadow: 0 2px 8px #bae6fd;
}
.reply-form .cancel-btn {
  background: #e5e7eb;
  color: #334155;
  box-shadow: none;
}
.replies {
  margin-top: 12px;
  padding-left: 16px;
  border-left: 2.5px solid #a5b4fc;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.reply-item {
  color: #334155;
  font-size: 1em;
  background: #f3f4f6;
  border-radius: 8px;
  padding: 7px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  box-shadow: 0 1px 4px rgba(59,130,246,0.04);
}
.reply-user {
  color: #3b82f6;
  font-weight: bold;
}
.reply-time {
  color: #a1a1aa;
  font-size: 0.95em;
}
</style>
