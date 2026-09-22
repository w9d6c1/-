import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  chatInternal,
  chatCustomer,
  chatStreamInternal,
  chatStreamCustomer,
  listThreads,
  fetchThreadMessages,
  submitFeedback,
  submitUnanswered,
  type ChatResponse,
  type Citation,
  type ImageInfo,
  type StreamDone,
  type ThreadMessage,
} from "@/api/agent";

export interface Message {
  id: string;
  role: "user" | "ai";
  content: string;
  confidence?: number;
  needsHuman?: boolean;
  faqHit?: boolean;
  isStreaming?: boolean;
  citations?: Citation[];
  images?: ImageInfo[];
  timestamp: number;
}

export type AgentType = "internal" | "customer";

export const useChatStore = defineStore("chat", () => {
  const messages = ref<Message[]>([]);
  const currentThreadId = ref<string>("");
  const agentType = ref<AgentType>("internal");
  const isStreaming = ref(false);
  const threadHistory = ref<{ id: string; title: string }[]>([]);
  const messagesMap = ref<Record<string, Message[]>>({});
  const ratedMessages = ref<Record<string, "like" | "dislike">>({});
  const lastUserQuestion = ref<string>("");

  const CUSTOMER_THREADS_KEY = "kb_customer_threads";

  function _readCustomerThreads(): { id: string; title: string }[] {
    try {
      return JSON.parse(localStorage.getItem(CUSTOMER_THREADS_KEY) || "[]");
    } catch {
      return [];
    }
  }

  function _rememberCustomerThread(id: string, title: string) {
    if (agentType.value !== "customer") return;
    const list = _readCustomerThreads();
    if (!list.some((t) => t.id === id)) {
      list.unshift({ id, title });
      try {
        localStorage.setItem(CUSTOMER_THREADS_KEY, JSON.stringify(list.slice(0, 50)));
      } catch {
        /* ignore quota */
      }
    }
  }

  async function initThreads() {
    if (agentType.value === "internal") {
      try {
        const rows = await listThreads();
        const known = new Set(threadHistory.value.map((t) => t.id));
        for (const r of rows) {
          if (!known.has(r.thread_id)) {
            threadHistory.value.push({ id: r.thread_id, title: r.title });
          }
        }
      } catch {
        /* best-effort */
      }
    } else {
      const known = new Set(threadHistory.value.map((t) => t.id));
      for (const t of _readCustomerThreads()) {
        if (!known.has(t.id)) threadHistory.value.push(t);
      }
    }
  }

  function _genId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function _saveCurrentThread() {
    if (currentThreadId.value && messages.value.length > 0) {
      messagesMap.value = {
        ...messagesMap.value,
        [currentThreadId.value]: [...messages.value],
      };
    }
  }

  function addUserMessage(content: string) {
    const msg: Message = {
      id: _genId(),
      role: "user",
      content,
      timestamp: Date.now(),
    };
    messages.value.push(msg);
    return msg;
  }

  function addAIMessage() {
    const msg: Message = {
      id: _genId(),
      role: "ai",
      content: "",
      isStreaming: true,
      timestamp: Date.now(),
    };
    messages.value.push(msg);
    return msg;
  }

  async function sendMessage(content: string) {
    if (isStreaming.value || !content.trim()) return;

    const isNew = !currentThreadId.value;
    if (isNew) {
      _saveCurrentThread();
      _ensureThread();
    }

    addUserMessage(content);
    lastUserQuestion.value = content;
    const aiMsg = addAIMessage();
    isStreaming.value = true;

    const streamFn = agentType.value === "customer" ? chatStreamCustomer : chatStreamInternal;

    try {
      for await (const event of streamFn(content, currentThreadId.value || undefined)) {
        if (event.type === "token") {
          aiMsg.content += event.content;
        } else if (event.type === "done") {
          aiMsg.content = event.answer || aiMsg.content;
          aiMsg.confidence = event.confidence;
          aiMsg.needsHuman = event.needs_human;
          aiMsg.faqHit = event.faq_hit;
          aiMsg.citations = event.citations || [];
          aiMsg.images = event.images || [];
          aiMsg.isStreaming = false;

          if (isNew) {
            threadHistory.value.unshift({
              id: currentThreadId.value,
              title: content.slice(0, 20),
            });
            _rememberCustomerThread(currentThreadId.value, content.slice(0, 20));
          }

          if (event.confidence !== undefined && event.confidence < 0.5 && lastUserQuestion.value) {
            submitUnanswered(
              currentThreadId.value,
              lastUserQuestion.value,
              agentType.value,
              agentType.value !== "customer",
            ).catch(() => {});
          }
        } else if (event.type === "error") {
          aiMsg.content = event.message || "抱歉，系统暂时出现问题，请稍后重试。";
          aiMsg.isStreaming = false;
        }
      }
    } catch (e: any) {
      if (e?.message === "Unauthorized") return;
      aiMsg.content = "抱歉，系统暂时出现问题，请稍后重试。";
      aiMsg.isStreaming = false;
    }

    isStreaming.value = false;
  }

  function _ensureThread() {
    if (!currentThreadId.value) {
      currentThreadId.value = _genId();
    }
  }

  function newThread() {
    _saveCurrentThread();
    messages.value = [];
    currentThreadId.value = "";
  }

  async function switchThread(id: string) {
    if (id === currentThreadId.value) return;
    _saveCurrentThread();
    currentThreadId.value = id;
    if (messagesMap.value[id] !== undefined && messagesMap.value[id].length > 0) {
      messages.value = [...messagesMap.value[id]];
      return;
    }
    // 后端水合
    messages.value = [];
    messagesMap.value = { ...messagesMap.value, [id]: [] };
    try {
      const rows = await fetchThreadMessages(id, agentType.value);
      const hydrated: Message[] = [];
      for (const m of rows) {
        hydrated.push({
          id: _genId(),
          role: "user",
          content: m.question,
          timestamp: new Date(m.created_at).getTime(),
        });
        if (m.answer) {
          hydrated.push({
            id: _genId(),
            role: "ai",
            content: m.answer,
            confidence: m.confidence ?? undefined,
            faqHit: m.faq_hit,
            citations: (m.citations ?? undefined) as Citation[] | undefined,
            images: (m.images ?? undefined) as ImageInfo[] | undefined,
            timestamp: new Date(m.created_at).getTime() + 1,
          });
        }
      }
      messagesMap.value = { ...messagesMap.value, [id]: hydrated };
      messages.value = [...hydrated];
    } catch {
      messagesMap.value = { ...messagesMap.value, [id]: [] };
    }
  }

  async function rateMessage(msgId: string, rating: "like" | "dislike") {
    if (ratedMessages.value[msgId]) return;
    ratedMessages.value = { ...ratedMessages.value, [msgId]: rating };
    try {
      await submitFeedback(currentThreadId.value, rating, undefined, agentType.value !== "customer");
    } catch {
      // silently fail – feedback is best-effort
    }
  }

  const lastConfidence = computed(() => {
    const last = messages.value.filter((m) => m.role === "ai").pop();
    return last?.confidence;
  });

  return {
    messages,
    currentThreadId,
    agentType,
    isStreaming,
    threadHistory,
    ratedMessages,
    sendMessage,
    rateMessage,
    newThread,
    switchThread,
    initThreads,
    lastConfidence,
  };
});
