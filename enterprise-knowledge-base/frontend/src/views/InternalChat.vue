<template>
  <el-container class="chat-page">
    <el-aside width="260px" class="chat-sidebar">
      <div class="sidebar-header">
        <el-button type="primary" @click="chat.newThread()" :icon="Plus">新对话</el-button>
      </div>
      <div class="thread-list">
        <div
          v-for="t in chat.threadHistory"
          :key="t.id"
          class="thread-item"
          :class="{ active: chat.currentThreadId === t.id }"
          @click="chat.switchThread(t.id)"
        >
          <span class="thread-title">{{ t.title }}</span>
        </div>
        <el-empty v-if="chat.threadHistory.length === 0" description="暂无对话记录" />
      </div>
    </el-aside>

    <el-container class="chat-main">
      <el-header class="chat-header">
        <span class="header-title">内部问答</span>
        <span class="header-info">内部知识库智能问答</span>
      </el-header>

      <el-main class="chat-body" ref="chatBodyRef">
        <div v-if="chat.messages.length === 0" class="empty-hint">
          <el-empty description="开始提问，获取知识库智能回答" />
        </div>
        <div
          v-for="msg in chat.messages"
          :key="msg.id"
          class="message-row"
          :class="msg.role"
        >
          <div class="message-bubble" :class="msg.role">
            <div class="msg-content">
              <CitationRenderer
                :content="msg.content"
                :citations="msg.citations"
                :images="msg.images"
                :is-streaming="msg.isStreaming"
              />
            </div>
            <div v-if="msg.role === 'ai'" class="msg-meta">
              <el-tag v-if="msg.confidence !== undefined" size="small" :type="confidenceType(msg.confidence)">
                置信度: {{ (msg.confidence * 100).toFixed(0) }}%
              </el-tag>
              <el-tag v-if="msg.faqHit" size="small" type="success">FAQ命中</el-tag>
              <el-tag v-if="msg.needsHuman" size="small" type="warning">建议转人工</el-tag>
              <span class="feedback-btns">
                <el-button
                  size="small"
                  text
                  :type="chat.ratedMessages[msg.id] === 'like' ? 'primary' : 'default'"
                  @click="chat.rateMessage(msg.id, 'like')"
                >👍 有帮助</el-button>
                <el-button
                  size="small"
                  text
                  :type="chat.ratedMessages[msg.id] === 'dislike' ? 'danger' : 'default'"
                  @click="chat.rateMessage(msg.id, 'dislike')"
                >👎 没帮助</el-button>
              </span>
            </div>
          </div>
        </div>
        <div v-if="chat.isStreaming && lastAIMsg?.isStreaming" class="typing-hint">AI 正在思考...</div>
      </el-main>

      <el-footer class="chat-footer">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="2"
          placeholder="请输入您的问题..."
          @keydown.enter.exact.prevent="handleSend"
          :disabled="chat.isStreaming"
        />
        <el-button
          type="primary"
          :icon="Promotion"
          @click="handleSend"
          :disabled="chat.isStreaming || !inputText.trim()"
        >发送</el-button>
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from "vue";
import { Plus, Promotion } from "@element-plus/icons-vue";
import { useChatStore } from "@/stores/chat";
import CitationRenderer from "@/components/CitationRenderer.vue";

const chat = useChatStore();
const inputText = ref("");
const chatBodyRef = ref<HTMLElement | null>(null);

onMounted(() => {
  chat.agentType = "internal";
});

const lastAIMsg = computed(() => {
  return chat.messages.filter((m) => m.role === "ai").pop();
});

function confidenceType(val: number | undefined): "success" | "warning" | "danger" | "info" {
  if (val === undefined) return "info";
  if (val >= 0.8) return "success";
  if (val >= 0.5) return "warning";
  return "danger";
}

async function handleSend() {
  const msg = inputText.value.trim();
  if (!msg || chat.isStreaming) return;
  inputText.value = "";
  await chat.sendMessage(msg);
  await nextTick();
  scrollToBottom();
}

watch(
  () => chat.messages.length,
  async () => {
    await nextTick();
    scrollToBottom();
  }
);

function scrollToBottom() {
  if (chatBodyRef.value) {
    chatBodyRef.value.scrollTop = chatBodyRef.value.scrollHeight;
  }
}
</script>

<style scoped>
.chat-page { height: 100vh; }
.chat-sidebar { background: #fff; border-right: 1px solid #ebeef5; display: flex; flex-direction: column; }
.sidebar-header { padding: 16px; border-bottom: 1px solid #ebeef5; }
.thread-list { flex: 1; overflow-y: auto; padding: 8px; }
.thread-item { padding: 10px 12px; border-radius: 6px; cursor: pointer; margin-bottom: 4px; }
.thread-item:hover { background: #f0f2f5; }
.thread-item.active { background: #ecf5ff; color: #409eff; }
.thread-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }

.chat-main { display: flex; flex-direction: column; }
.chat-header { background: #fff; border-bottom: 1px solid #ebeef5; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; height: 56px; }
.header-title { font-size: 16px; font-weight: 600; color: #303133; }
.header-info { font-size: 14px; color: #909399; }

.chat-body { flex: 1; overflow-y: auto; padding: 20px 40px; background: #f5f7fa; }
.empty-hint { display: flex; justify-content: center; align-items: center; height: 100%; }

.message-row { display: flex; margin-bottom: 16px; }
.message-row.user { justify-content: flex-end; }
.message-row.ai { justify-content: flex-start; }

.message-bubble { max-width: 70%; padding: 12px 16px; border-radius: 12px; font-size: 14px; line-height: 1.6; }
.message-bubble.user { background: #409eff; color: #fff; border-bottom-right-radius: 4px; }
.message-bubble.ai { background: #fff; border: 1px solid #ebeef5; border-bottom-left-radius: 4px; }
.msg-meta { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.feedback-btns { margin-left: auto; }
.msg-content { word-break: break-word; }

.typing-hint { font-size: 12px; color: #909399; padding: 4px 0 0 40px; }

.chat-footer { background: #fff; border-top: 1px solid #ebeef5; display: flex; gap: 12px; align-items: flex-end; padding: 12px 20px; height: auto; }
.chat-footer .el-textarea { flex: 1; }
</style>
