import { getToken, clearToken } from "@/stores/auth";

const BASE = "/api/agent";

function h(extra?: Record<string, string>) {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${getToken()}`,
    "Content-Type": "application/json",
  };
  if (extra) Object.assign(headers, extra);
  return headers;
}

function h_public(extra?: Record<string, string>) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (extra) Object.assign(headers, extra);
  return headers;
}

function _handleAuthError() {
  clearToken();
  window.location.hash = "#/login";
}

export interface ImageInfo {
  id: number;
  doc_index: number;
  seq: number;
  url: string;
  object_name?: string;
  width?: number | null;
  height?: number | null;
}

export interface Citation {
  index: number;
  title: string;
  platform: string;
  url: string;
  source_name: string;
  is_internal: boolean;
  images?: { id: number; url: string; width?: number | null; height?: number | null }[];
}

export interface ChatRequest {
  message: string;
  thread_id?: string;
}

export interface ChatResponse {
  thread_id: string;
  answer: string;
  is_blocked: boolean;
  block_reason: string;
  confidence: number;
  needs_human: boolean;
  human_reason?: string;
  faq_hit: boolean;
  route: string;
  citations?: Citation[];
  images?: ImageInfo[];
}

export interface AgentInfo {
  status: string;
  modules: Record<string, string>;
}

export interface StreamToken {
  type: "token";
  content: string;
}

export interface StreamDone {
  type: "done";
  answer: string;
  confidence: number;
  needs_human: boolean;
  faq_hit: boolean;
  citations?: Citation[];
  images?: ImageInfo[];
}

export interface StreamError {
  type: "error";
  message: string;
}

async function _chat(url: string, msg: string, threadId?: string): Promise<ChatResponse> {
  const resp = await fetch(url, {
    method: "POST",
    headers: h(),
    body: JSON.stringify({ message: msg, thread_id: threadId }),
  });
  if (resp.status === 401) {
    _handleAuthError();
    throw new Error("Unauthorized");
  }
  return resp.json();
}

export async function chatInternal(msg: string, threadId?: string): Promise<ChatResponse> {
  return _chat(`${BASE}/internal/chat`, msg, threadId);
}

export async function chatCustomer(msg: string, threadId?: string): Promise<ChatResponse> {
  const resp = await fetch(`${BASE}/customer/chat`, {
    method: "POST",
    headers: h_public(),
    body: JSON.stringify({ message: msg, thread_id: threadId }),
  });
  return resp.json();
}

async function* _chatStream(url: string, msg: string, threadId?: string): AsyncGenerator<StreamToken | StreamDone | StreamError> {
  const resp = await fetch(url, {
    method: "POST",
    headers: h(),
    body: JSON.stringify({ message: msg, thread_id: threadId }),
  });

  if (resp.status === 401) {
    _handleAuthError();
    throw new Error("Unauthorized");
  }

  const reader = resp.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6);
        if (data === "[DONE]") return;
        try {
          const parsed = JSON.parse(data) as StreamToken | StreamDone | StreamError;
          yield parsed;
        } catch {
          // skip malformed SSE lines
        }
      }
    }
  }
}

async function* _chatStreamPublic(url: string, msg: string, threadId?: string): AsyncGenerator<StreamToken | StreamDone | StreamError> {
  const resp = await fetch(url, {
    method: "POST",
    headers: h_public(),
    body: JSON.stringify({ message: msg, thread_id: threadId }),
  });

  const reader = resp.body?.getReader();
  if (!reader) return;

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = line.slice(6);
        if (data === "[DONE]") return;
        try {
          const parsed = JSON.parse(data) as StreamToken | StreamDone | StreamError;
          yield parsed;
        } catch {
          // skip malformed SSE lines
        }
      }
    }
  }
}

export async function* chatStreamInternal(msg: string, threadId?: string): AsyncGenerator<StreamToken | StreamDone | StreamError> {
  yield* _chatStream(`${BASE}/internal/chat/stream`, msg, threadId);
}

export async function* chatStreamCustomer(msg: string, threadId?: string): AsyncGenerator<StreamToken | StreamDone | StreamError> {
  yield* _chatStreamPublic(`${BASE}/customer/chat/stream`, msg, threadId);
}

export async function submitFeedback(
  threadId: string,
  rating: "like" | "dislike",
  suggestion?: string,
  useAuth: boolean = true,
): Promise<void> {
  const headersFn = useAuth ? h : h_public;
  await fetch(`${BASE}/../admin/feedbacks`, {
    method: "POST",
    headers: headersFn(),
    body: JSON.stringify({ thread_id: threadId, rating, suggestion: suggestion || null }),
  });
}

export async function submitUnanswered(
  threadId: string,
  question: string,
  source: string = "customer",
  useAuth: boolean = true,
): Promise<void> {
  const headersFn = useAuth ? h : h_public;
  await fetch(`${BASE}/../admin/unanswered`, {
    method: "POST",
    headers: headersFn(),
    body: JSON.stringify({ thread_id: threadId, question, source }),
  });
}

export async function getAgentStatus(): Promise<{ status: string }> {
  const resp = await fetch(`${BASE}/status`, { headers: h() });
  return resp.json();
}

export async function getAgentInfo(): Promise<AgentInfo> {
  const resp = await fetch(`${BASE}/info`, { headers: h() });
  return resp.json();
}

export interface ThreadSummary {
  thread_id: string;
  title: string;
  turns: number;
  last_active: string;
}

export interface ThreadMessage {
  question: string;
  answer: string;
  confidence?: number | null;
  faq_hit: boolean;
  citations?: Citation[] | null;
  images?: ImageInfo[] | null;
  created_at: string;
}

export async function listThreads(): Promise<ThreadSummary[]> {
  const resp = await fetch(`${BASE}/threads?limit=50`, { headers: h() });
  if (resp.status === 401) {
    _handleAuthError();
    throw new Error("Unauthorized");
  }
  return resp.json();
}

export async function fetchThreadMessages(threadId: string, source: string): Promise<ThreadMessage[]> {
  const headersFn = source === "internal" ? h : h_public;
  const resp = await fetch(
    `${BASE}/threads/${encodeURIComponent(threadId)}/messages?source=${source}`,
    { headers: headersFn() },
  );
  if (!resp.ok) return [];
  return resp.json();
}
