import express from 'express';
import { WebSocketServer } from 'ws';
import { pathToFileURL } from 'node:url';

const PORT = 3010;
const REQUEST_TIMEOUT_MS = 360_000; // 6 分钟（与 CLI 一致，图片多时需要更长时间）

const GROUP_PORTS = {
  '2113': { ws: 9531 },
  '2114': { ws: 9533 },
  '2119': { ws: 9535 },
  '9023': { ws: 9537 },
};

// ============================================================
// 每组状态：常驻 WS 服务 + 扩展连接 + 串行队列
// ============================================================

const KEEPALIVE_INTERVAL_MS = 20_000; // 心跳间隔，防止 Chrome MV3 service worker 空闲回收

export function createGroupStates() {
  const groups = {};
  for (const [g, ports] of Object.entries(GROUP_PORTS)) {
    groups[g] = {
      wsPort: ports.ws,
      client: null,        // 当前扩展连接
      keepAlive: null,     // 心跳定时器
      lastToken: '',       // 最近一次发布使用的 token（供心跳复用）
      pending: new Map(),  // id -> { resolve, reject, timeout }
      queue: [],
      running: false,
    };
  }
  return groups;
}

export function startGroupServer(group, groups) {
  const state = groups[group];
  const wss = new WebSocketServer({ port: state.wsPort });

  wss.on('listening', () => {
    console.log(`[${group}] WS 常驻监听: ws://0.0.0.0:${state.wsPort}`);
  });

  wss.on('connection', (ws) => {
    console.log(`[${group}] Chrome 扩展已连接`);
    state.client = ws;

    // 周期性心跳：WS 消息作为事件唤醒/保活扩展的 service worker
    if (state.keepAlive) clearInterval(state.keepAlive);
    state.keepAlive = setInterval(() => {
      if (ws.readyState === 1) {
        ws.send(JSON.stringify({ id: generateId(), method: 'ping', token: state.lastToken, params: {} }));
      }
    }, KEEPALIVE_INTERVAL_MS);

    ws.on('message', (data) => handleMessage(group, data.toString(), groups));
    ws.on('close', () => {
      if (state.client === ws) {
        state.client = null;
        if (state.keepAlive) {
          clearInterval(state.keepAlive);
          state.keepAlive = null;
        }
        console.log(`[${group}] Chrome 扩展已断开`);
        for (const [id, p] of state.pending) {
          clearTimeout(p.timeout);
          p.reject(new Error('Chrome 扩展连接已断开'));
          state.pending.delete(id);
        }
      }
    });
    ws.on('error', (err) => {
      console.error(`[${group}] WS 连接错误: ${err.message}`);
    });
  });

  wss.on('error', (err) => {
    console.error(`[${group}] WS 服务错误: ${err.message}`);
  });
}

export function handleMessage(group, data, groups) {
  const state = groups[group];
  let msg;
  try {
    msg = JSON.parse(data);
  } catch {
    console.error(`[${group}] 无法解析扩展消息`);
    return;
  }
  const pending = state.pending.get(msg.id);
  if (!pending) return;
  clearTimeout(pending.timeout);
  state.pending.delete(msg.id);
  if (msg.error) {
    pending.reject(new Error(msg.error.message || JSON.stringify(msg.error)));
  } else {
    pending.resolve(msg.result);
  }
}

export function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

// 向扩展发送请求（协议与 @wechatsync/cli 一致: {id, method, token, params}）
export function request(group, token, method, params, groups) {
  const state = groups[group];
  if (!state.client || state.client.readyState !== 1) {
    return Promise.reject(new Error(
      `Chrome 扩展未连接（请确认 ${group} 浏览器身份已打开、扩展已启用「CLI / MCP 连接」且服务器地址为 ws://localhost:${state.wsPort}）`
    ));
  }
  const id = generateId();
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      state.pending.delete(id);
      reject(new Error(`扩展响应超时: ${method}`));
    }, REQUEST_TIMEOUT_MS);
    state.pending.set(id, { resolve, reject, timeout });
    state.client.send(JSON.stringify({ id, method, token, params }));
  });
}

// ============================================================
// Markdown → HTML（与 @wechatsync/cli 的 markdownToHtml 一致）
// ============================================================

export function markdownToHtml(markdown) {
  let html = markdown;
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" />');
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  html = html.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>');
  html = html.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>');
  html = html.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>');
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/^\s*[-*+]\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  html = html.replace(/^\s*\d+\.\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/^>\s+(.+)$/gm, '<blockquote>$1</blockquote>');
  html = html.replace(/^---+$/gm, '<hr />');
  html = html.replace(/^(?!<[a-z])((?:[^\n]+\n?)+)/gm, (match) => {
    const trimmed = match.trim();
    if (trimmed && !trimmed.startsWith('<')) {
      return `<p>${trimmed}</p>\n`;
    }
    return match;
  });
  return html;
}

// ============================================================
// 发布执行
// ============================================================

export async function executePublish(group, title, content, platform, token, markdown, groups) {
  groups[group].lastToken = token;
  console.log(`[${group}] 发布中: ${title} → ${platform}`);
  try {
    // 后端已解析 [IMAGE] 标记：
    // - content 为含 base64 图片的 HTML，优先直接使用
    // - markdown 为含公开 URL 图片的 Markdown，供扩展解析下载
    const articleMarkdown = markdown || content;
    const articleContent = content || markdownToHtml(articleMarkdown);
    const response = await request(group, token, 'syncArticle', {
      platforms: [platform],
      article: {
        title,
        markdown: articleMarkdown,
        content: articleContent,
      },
    }, groups);

    const results = response?.results || [];
    const r = results.find((x) => x.platform === platform) || results[0];
    if (!r) {
      return { success: false, error: '扩展未返回同步结果' };
    }
    if (r.success) {
      console.log(`[${group}] 发布成功: ${title}${r.postUrl ? ' → ' + r.postUrl : ''}`);
      return { success: true, url: r.postUrl || null };
    }
    console.error(`[${group}] 发布失败: ${r.error || '未知错误'}`);
    return { success: false, error: r.error || '未知错误' };
  } catch (err) {
    console.error(`[${group}] 发布失败: ${err.message}`);
    return { success: false, error: err.message };
  }
}

export function processQueue(group, groups) {
  const state = groups[group];
  if (state.running) return;
  const task = state.queue.shift();
  if (!task) return;
  state.running = true;
  task();
}

// ============================================================
// HTTP 服务
// ============================================================

export function createApp(groups) {
  const app = express();
  app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    if (req.method === 'OPTIONS') return res.sendStatus(204);
    next();
  });
  app.use(express.json({ limit: '50mb' }));

  app.get('/health', (_req, res) => {
    res.json({
      ok: true,
      service: 'enterprise-kb-publisher-bridge',
      mode: 'resident-ws-gateway',
      group_ports: Object.fromEntries(
        Object.entries(GROUP_PORTS).map(([g, p]) => [g, { ws: p.ws }])
      ),
      extension_connected: Object.fromEntries(
        Object.entries(groups).map(([g, s]) => [g, !!(s.client && s.client.readyState === 1)])
      ),
      queue_lengths: Object.fromEntries(
        Object.entries(groups).map(([g, s]) => [g, s.queue.length])
      ),
      running: Object.fromEntries(
        Object.entries(groups).map(([g, s]) => [g, s.running])
      ),
    });
  });

  app.post('/api/publish', async (req, res) => {
    const { title, content, markdown, platform, group, token } = req.body;

    if (!title || !content || !platform || !group || !token) {
      return res.status(400).json({
        success: false,
        error: '缺少必要参数 (title, content, platform, group, token)',
      });
    }

    if (!groups[group]) {
      return res.status(400).json({
        success: false,
        error: `未知账号组: ${group}，有效值: ${Object.keys(groups).join(', ')}`,
      });
    }

    const state = groups[group];
    state.queue.push(async () => {
      try {
        const result = await executePublish(group, title, content, platform, token, markdown, groups);
        res.json(result);
      } catch (err) {
        res.status(500).json({ success: false, error: err.message });
      } finally {
        state.running = false;
        processQueue(group, groups);
      }
    });

    processQueue(group, groups);
  });

  return app;
}

// ============================================================
// 启动（仅直接运行时执行，便于测试导入）
// ============================================================

const groups = createGroupStates();
const app = createApp(groups);

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;

if (isMain) {
  for (const g of Object.keys(groups)) {
    startGroupServer(g, groups);
  }

  app.listen(PORT, () => {
    console.log(`发布桥接器已启动: http://localhost:${PORT} (常驻 WS 网关模式)`);
    console.log('账号组 WS 端口:');
    for (const [g, p] of Object.entries(GROUP_PORTS)) {
      console.log(`  ${g} → ws://localhost:${p.ws}`);
    }
  });
}
