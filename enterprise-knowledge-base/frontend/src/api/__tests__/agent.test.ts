import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

vi.mock("@/stores/auth", () => ({
  getToken: () => localStorage.getItem("token") || "",
  clearToken: () => localStorage.removeItem("token"),
}));

import {
  chatCustomer,
  chatInternal,
  chatStreamCustomer,
  chatStreamInternal,
  listThreads,
} from "@/api/agent";

const fetchMock = vi.fn();

function sseBody(lines: string[]): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(lines.join("\n")));
      controller.close();
    },
  });
}

describe("agent API", () => {
  beforeEach(() => {
    localStorage.clear();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = "";
  });

  it("chatCustomer posts to customer endpoint without auth headers", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ thread_id: "t", answer: "客服回答" }),
    });
    const result = await chatCustomer("问题", "t-1");
    expect(result.answer).toBe("客服回答");

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/agent/customer/chat");
    expect(JSON.parse(init.body)).toEqual({ message: "问题", thread_id: "t-1" });
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBeUndefined();
  });

  it("chatInternal includes the Bearer token", async () => {
    localStorage.setItem("token", "jwt-1");
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ thread_id: "t", answer: "ok" }),
    });
    await chatInternal("hello");
    const init = fetchMock.mock.calls[0][1];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer jwt-1");
  });

  it("chatInternal redirects to login and throws on 401", async () => {
    localStorage.setItem("token", "expired");
    fetchMock.mockResolvedValue({ ok: false, status: 401 });
    await expect(chatInternal("hello")).rejects.toThrow("Unauthorized");
    expect(localStorage.getItem("token")).toBeNull();
    expect(window.location.hash).toContain("#/login");
  });

  it("chatStreamCustomer parses SSE token/done/[DONE] events", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      body: sseBody([
        'data: {"type":"token","content":"你"}',
        'data: {"type":"done","answer":"你好","confidence":0.9,"needs_human":false,"faq_hit":true}',
        "data: [DONE]",
      ]),
    });
    const events: unknown[] = [];
    for await (const e of chatStreamCustomer("你好")) events.push(e);
    expect(events).toHaveLength(2);
    expect((events[0] as { type: string }).type).toBe("token");
    expect((events[1] as { type: string }).type).toBe("done");
    expect((events[1] as { answer: string }).answer).toBe("你好");
  });

  it("chatStreamInternal skips malformed SSE lines", async () => {
    localStorage.setItem("token", "jwt");
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      body: sseBody([
        "data: not-json",
        'data: {"type":"token","content":"hi"}',
        "data: [DONE]",
      ]),
    });
    const events: unknown[] = [];
    for await (const e of chatStreamInternal("hi")) events.push(e);
    expect(events).toHaveLength(1);
    expect((events[0] as { content: string }).content).toBe("hi");
  });

  it("chatStreamInternal handles 401 by redirecting and throwing", async () => {
    localStorage.setItem("token", "expired");
    fetchMock.mockResolvedValue({ ok: false, status: 401 });
    await expect(
      (async () => {
        for await (const _ of chatStreamInternal("hi")) {
          /* drain */
        }
      })(),
    ).rejects.toThrow("Unauthorized");
    expect(window.location.hash).toContain("#/login");
  });

  it("listThreads returns thread summaries", async () => {
    localStorage.setItem("token", "jwt");
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [{ thread_id: "t1", title: "会话", turns: 2 }],
    });
    const rows = await listThreads();
    expect(rows).toHaveLength(1);
    expect(fetchMock.mock.calls[0][0]).toContain("/api/agent/threads");
  });
});
