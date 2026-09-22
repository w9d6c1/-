import { describe, it, expect, beforeEach, vi } from "vitest";
import { setActivePinia, createPinia } from "pinia";

vi.mock("@/api/agent", () => ({
  chatInternal: vi.fn(),
  chatCustomer: vi.fn(),
  chatStreamInternal: vi.fn(),
  chatStreamCustomer: vi.fn(),
  listThreads: vi.fn(),
  fetchThreadMessages: vi.fn(),
  submitFeedback: vi.fn(),
  submitUnanswered: vi.fn(),
}));

import {
  chatStreamInternal,
  chatStreamCustomer,
  listThreads,
  fetchThreadMessages,
  submitFeedback,
  submitUnanswered,
} from "@/api/agent";
import { useChatStore } from "@/stores/chat";

const mockStreamInternal = vi.mocked(chatStreamInternal);
const mockStreamCustomer = vi.mocked(chatStreamCustomer);
const mockListThreads = vi.mocked(listThreads);
const mockFetchThreadMessages = vi.mocked(fetchThreadMessages);
const mockSubmitFeedback = vi.mocked(submitFeedback);
const mockSubmitUnanswered = vi.mocked(submitUnanswered);

async function* genStream(
  events: unknown[],
): AsyncGenerator<{ type: string; [k: string]: unknown }> {
  for (const e of events) yield e as { type: string; [k: string]: unknown };
}

describe("chat store", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
    vi.clearAllMocks();
  });

  it("creates a user message before the AI message during send", async () => {
    mockStreamInternal.mockReturnValue(
      genStream([
        {
          type: "done",
          answer: "ok",
          confidence: 0.9,
          needs_human: false,
          faq_hit: false,
          citations: [],
          images: [],
        },
      ]) as never,
    );
    const store = useChatStore();
    await store.sendMessage("你好");
    expect(store.messages[0].role).toBe("user");
    expect(store.messages[0].content).toBe("你好");
    expect(store.messages[1].role).toBe("ai");
  });

  it("sendMessage streams tokens and finalizes on done", async () => {
    mockStreamInternal.mockReturnValue(
      genStream([
        { type: "token", content: "你" },
        { type: "token", content: "好" },
        {
          type: "done",
          answer: "你好世界",
          confidence: 0.92,
          needs_human: false,
          faq_hit: true,
          citations: [],
          images: [],
        },
      ]) as never,
    );

    const store = useChatStore();
    await store.sendMessage("打招呼");

    const aiMsg = store.messages.find((m) => m.role === "ai");
    expect(aiMsg?.content).toBe("你好世界");
    expect(aiMsg?.isStreaming).toBe(false);
    expect(aiMsg?.confidence).toBe(0.92);
    expect(aiMsg?.faqHit).toBe(true);
    expect(store.isStreaming).toBe(false);
  });

  it("sendMessage is a no-op while streaming or for blank input", async () => {
    const store = useChatStore();
    store.isStreaming = true;
    await store.sendMessage("should be ignored");
    expect(mockStreamInternal).not.toHaveBeenCalled();

    store.isStreaming = false;
    await store.sendMessage("   ");
    expect(mockStreamInternal).not.toHaveBeenCalled();
  });

  it("sendMessage surfaces an error event into the message", async () => {
    mockStreamInternal.mockReturnValue(
      genStream([{ type: "error", message: "AI 服务暂不可用" }]) as never,
    );
    const store = useChatStore();
    await store.sendMessage("问题");
    const aiMsg = store.messages.find((m) => m.role === "ai");
    expect(aiMsg?.content).toBe("AI 服务暂不可用");
    expect(aiMsg?.isStreaming).toBe(false);
  });

  it("auto-submits unanswered question when confidence is low", async () => {
    mockStreamInternal.mockReturnValue(
      genStream([
        {
          type: "done",
          answer: "未找到",
          confidence: 0.3,
          needs_human: true,
          faq_hit: false,
          citations: [],
          images: [],
        },
      ]) as never,
    );
    const store = useChatStore();
    await store.sendMessage("这个很冷门");
    await vi.waitFor(() => expect(mockSubmitUnanswered).toHaveBeenCalled());
  });

  it("does not auto-submit when confidence is high", async () => {
    mockStreamInternal.mockReturnValue(
      genStream([
        {
          type: "done",
          answer: "ok",
          confidence: 0.9,
          needs_human: false,
          faq_hit: true,
          citations: [],
          images: [],
        },
      ]) as never,
    );
    const store = useChatStore();
    await store.sendMessage("常见问题");
    expect(mockSubmitUnanswered).not.toHaveBeenCalled();
  });

  it("rateMessage submits feedback and remembers the rating", async () => {
    const store = useChatStore();
    await store.sendMessage("x"); // creates a thread id
    const aiMsg = store.messages.find((m) => m.role === "ai");
    await store.rateMessage(aiMsg!.id, "like");
    expect(mockSubmitFeedback).toHaveBeenCalledWith(
      expect.any(String),
      "like",
      undefined,
      true,
    );
    expect(store.ratedMessages[aiMsg!.id]).toBe("like");
  });

  it("initThreads loads internal thread history from the API", async () => {
    mockListThreads.mockResolvedValue([
      { thread_id: "t-1", title: "历史会话", turns: 2, last_active: "2026-01-01T00:00:00" },
    ] as never);
    const store = useChatStore();
    await store.initThreads();
    expect(store.threadHistory).toEqual([{ id: "t-1", title: "历史会话" }]);
  });

  it("switchThread hydrates messages from the server", async () => {
    mockFetchThreadMessages.mockResolvedValue([
      {
        question: "请假流程",
        answer: "填写请假单",
        confidence: 0.8,
        faq_hit: true,
        created_at: "2026-01-01T00:00:00",
      },
    ] as never);
    const store = useChatStore();
    await store.switchThread("t-9");
    expect(store.currentThreadId).toBe("t-9");
    expect(store.messages).toHaveLength(2);
    expect(store.messages[0].role).toBe("user");
    expect(store.messages[1].role).toBe("ai");
    expect(store.messages[1].content).toBe("填写请假单");
  });

  it("customer thread history is persisted to localStorage", async () => {
    mockStreamCustomer.mockReturnValue(
      genStream([
        {
          type: "done",
          answer: "客服回答",
          confidence: 0.9,
          needs_human: false,
          faq_hit: true,
          citations: [],
          images: [],
        },
      ]) as never,
    );
    const store = useChatStore();
    store.agentType = "customer";
    await store.sendMessage("售后问题");
    const raw = localStorage.getItem("kb_customer_threads");
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw!)).toHaveLength(1);
  });

  it("newThread clears messages and thread id", async () => {
    mockStreamInternal.mockReturnValue(
      genStream([
        {
          type: "done",
          answer: "x",
          confidence: 0.9,
          needs_human: false,
          faq_hit: false,
          citations: [],
          images: [],
        },
      ]) as never,
    );
    const store = useChatStore();
    await store.sendMessage("q1");
    store.newThread();
    expect(store.messages).toHaveLength(0);
    expect(store.currentThreadId).toBe("");
  });
});
