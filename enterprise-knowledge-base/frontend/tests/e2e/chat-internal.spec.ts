import { test, expect } from "@playwright/test";

test.describe("Internal chat error handling", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      try {
        localStorage.setItem("token", "fake-token-value");
      } catch {
        /* about:blank */
      }
    });
    await page.route("**/api/admin/auth/me", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: 1,
          username: "tester",
          role: "operator",
          department: "运营部",
        }),
      });
    });
  });

  test("shows friendly message when the stream returns an error event", async ({ page }) => {
    await page.route("**/api/agent/internal/chat/stream", (route) => {
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: [
          'data: {"type":"token","content":"正在查询..."}\n',
          'data: {"type":"error","message":"AI 服务暂不可用，请稍后重试"}\n',
          "data: [DONE]\n",
        ].join("\n"),
      });
    });

    await page.goto("/#/chat/internal");
    await page.waitForLoadState("networkidle");

    const input = page.locator('textarea[placeholder*="请输入"]');
    await expect(input).toBeVisible();

    await input.fill("测试错误场景");
    await input.press("Enter");

    await expect(page.locator("text=AI 服务暂不可用，请稍后重试")).toBeVisible({ timeout: 10000 });
  });

  test("renders a needs-human response with the transfer hint", async ({ page }) => {
    await page.route("**/api/agent/internal/chat/stream", (route) => {
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: [
          'data: {"type":"done","answer":"建议您转人工客服处理。","confidence":0.4,"needs_human":true,"faq_hit":false,"citations":[],"images":[]}\n',
          "data: [DONE]\n",
        ].join("\n"),
      });
    });

    await page.goto("/#/chat/internal");
    await page.waitForLoadState("networkidle");

    const input = page.locator('textarea[placeholder*="请输入"]');
    await input.fill("我要投诉");
    await input.press("Enter");

    await expect(page.locator("text=建议您转人工客服处理。")).toBeVisible({ timeout: 10000 });
  });
});
