// 静态演示模式：拦截所有 /api/* 请求，返回内存中的模拟数据。
// 仅当构建时传入 VITE_DEMO=1 才启用，不影响真实生产构建。
// 用途：在没有后端的情况下，让前端页面可以完整浏览（数据均为模拟）。
import axios from "axios";

const ENABLED = import.meta.env.VITE_DEMO === "1";

function encode(value: string): string {
  return btoa(unescape(encodeURIComponent(value)));
}

function demoToken(): string {
  const header = encode(JSON.stringify({ alg: "none", typ: "JWT" }));
  const payload = encode(
    JSON.stringify({
      sub: "1",
      username: "demo",
      role: "admin",
      department: "Engineering",
      exp: 4102444800,
    }),
  );
  return `${header}.${payload}.demo-signature`;
}

const DEMO_USER = {
  id: 1,
  username: "demo",
  phone: "13800000000",
  display_name: "演示管理员",
  email: "demo@example.com",
  role: "admin",
  department: "Engineering",
  is_active: true,
  created_at: "2026-01-01T00:00:00",
};

const CITATIONS = [
  {
    index: 1,
    title: "员工手册（2026 版）",
    platform: "internal",
    url: "#",
    source_name: "内部知识库",
    is_internal: true,
  },
  {
    index: 2,
    title: "产品售后服务政策",
    platform: "official",
    url: "#",
    source_name: "官网",
    is_internal: false,
  },
];

const DEMO_ANSWER =
  "【演示数据】当前为静态演示环境，未连接后端。示例内容：入职满 1 年可享 5 天年假，满 3 年 10 天；售后支持 7 天无理由退换。真实回答由 RAG + LangGraph 智能体生成。";

function trendPoints(): { date: string; count: number }[] {
  const out: { date: string; count: number }[] = [];
  for (let i = 6; i >= 0; i -= 1) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    out.push({ date: d.toISOString().slice(0, 10), count: 12 + ((i * 9) % 27) });
  }
  return out;
}

function emptyPage() {
  return { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function sse(events: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const event of events) controller.enqueue(encoder.encode(event));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}

function chatStream(): Response {
  const chunks = [
    "【演示数据】",
    "这是一段",
    "静态演示环境的",
    "示例回答，",
    "未连接真实后端。",
    "真实场景下由 ",
    "RAG + 智能体",
    "流式生成。",
  ];
  const events = chunks.map((c) => `data: ${JSON.stringify({ type: "token", content: c })}\n\n`);
  events.push(
    `data: ${JSON.stringify({
      type: "done",
      answer: DEMO_ANSWER,
      confidence: 0.92,
      needs_human: false,
      faq_hit: false,
      citations: CITATIONS,
      images: [],
    })}\n\n`,
  );
  events.push("data: [DONE]\n\n");
  return sse(events);
}

function batchStream(): Response {
  return sse([
    `data: ${JSON.stringify({ type: "progress", batch_id: 1, message: "演示：生成中 50%" })}\n\n`,
    `data: ${JSON.stringify({ type: "completed", batch_id: 1, message: "演示：生成完成" })}\n\n`,
    "data: [DONE]\n\n",
  ]);
}

// 这些接口返回数组而非分页对象
const ARRAY_PATHS = [
  "/categories/tree",
  "/admin/categories",
  "/platforms",
  "/articles/accounts",
  "/templates",
  "/departments",
  "/chunks",
  "/versions",
  "/publishing-status",
  "/scope-permissions",
  "/unanswered",
  "/sync-states",
  "/agent/threads",
];

function mockResponse(pathname: string, method: string): Response {
  const m = method.toUpperCase();

  if (pathname.endsWith("/api/health")) {
    return json({
      status: "ok",
      demo: true,
      version: "0.1.0-demo",
      services: { mysql: "ok", redis: "ok", milvus: "ok", elasticsearch: "ok", minio: "ok" },
    });
  }

  if (pathname.includes("/admin/auth/send-code")) return json({ status: "ok", code: "123456" });
  if (pathname.includes("/admin/auth/phone-login") || pathname.includes("/admin/auth/login")) {
    return json({ access_token: demoToken(), token_type: "bearer", user: DEMO_USER });
  }
  if (pathname.includes("/admin/auth/me")) return json(DEMO_USER);

  if (pathname.includes("/agent/status")) return json({ status: "ok" });
  if (pathname.includes("/agent/info")) {
    return json({
      status: "ok",
      modules: { retriever: "demo", reranker: "demo", generator: "demo" },
    });
  }
  if (pathname.includes("/agent/") && pathname.includes("/chat") && pathname.includes("/stream")) {
    return chatStream();
  }
  if (pathname.includes("/agent/") && pathname.includes("/chat")) {
    return json({
      thread_id: "demo-thread",
      answer: DEMO_ANSWER,
      is_blocked: false,
      block_reason: "",
      confidence: 0.92,
      needs_human: false,
      human_reason: "",
      faq_hit: false,
      route: "demo",
      citations: CITATIONS,
      images: [],
    });
  }

  if (pathname.includes("/batches/") && pathname.endsWith("/stream")) return batchStream();

  if (pathname.includes("/admin/dashboard/stats")) {
    return json({
      today_chats: 128,
      faq_hit_rate: 0.76,
      feedback_good_rate: 0.93,
      pending_reviews: 4,
      pending_unanswered: 7,
      trend: trendPoints(),
    });
  }
  if (pathname.includes("/admin/feedbacks/stats")) {
    return json({ good: 42, bad: 3, total: 45, good_rate: 0.93 });
  }

  if (pathname.includes("/admin/articles/publishing-stats")) {
    return json({ total: 0, published: 0, pending: 0, failed: 0, by_platform: [] });
  }
  if (pathname.includes("/admin/articles/hot-topics")) {
    return json({ items: [], hot_topics: [], updated_at: Date.now(), hot_count: 0, message: "演示数据" });
  }
  if (pathname.includes("/admin/articles/bridge/status")) {
    return json({ ok: true, service: "demo", mode: "static", extension_connected: {}, queue_lengths: {}, running: {} });
  }

  if (m === "GET") {
    if (ARRAY_PATHS.some((p) => pathname.includes(p))) return json([]);
    return json(emptyPage());
  }

  return json({ status: "ok" });
}

function install(): void {
  // 1) 预置登录态，让路由守卫放行
  try {
    localStorage.setItem("token", demoToken());
    localStorage.setItem(
      "user",
      JSON.stringify({ id: 1, username: "demo", role: "admin", department: "Engineering" }),
    );
  } catch {
    // 存储不可用时忽略
  }

  // 2) 让 axios 走 fetch 适配器，从而命中下面的 fetch 拦截
  axios.defaults.adapter = "fetch";

  // 3) 拦截全局 fetch
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    let url = "";
    let method = "GET";

    if (typeof input === "string") {
      url = input;
    } else if (input instanceof URL) {
      url = input.href;
    } else {
      url = input.url;
      method = input.method || method;
    }
    if (init?.method) method = init.method;

    const resolved = new URL(url, window.location.origin);
    if (resolved.pathname.startsWith("/api/")) {
      return Promise.resolve(mockResponse(resolved.pathname, method));
    }
    return originalFetch(input, init);
  };

  // eslint-disable-next-line no-console
  console.info("[demo] 静态演示模式已启用：所有 /api/* 请求返回模拟数据。");
}

if (ENABLED) install();
