import { test, expect } from "@playwright/test";

test.describe("CitationRenderer in chat UI", () => {
  test.beforeEach(async ({ page }) => {
    page.on("dialog", (dialog) => dialog.accept());
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

  test("renders citation markers as clickable sup elements after response", async ({ page }) => {
    await page.route("**/api/agent/internal/chat/stream", (route) => {
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: [
          'data: {"type":"token","content":"根据[1]的记载。"}\n',
          'data: {"type":"done","answer":"根据[1]的记载。","confidence":0.9,"needs_human":false,"faq_hit":false,"citations":[{"index":1,"title":"入职手册","platform":"internal","url":"","source_name":"","is_internal":true}]}\n',
          "data: [DONE]\n",
        ].join("\n"),
      });
    });

    await page.goto("/#/chat/internal");
    await page.waitForLoadState("networkidle");

    const input = page.locator('textarea[placeholder*="请输入"]');
    await expect(input).toBeVisible();

    const hasToken = await page.evaluate(() => !!localStorage.getItem("token"));
    if (!hasToken) {
      test.skip(true, "Requires auth token in localStorage");
      return;
    }

    await input.fill("考勤制度查询");
    await input.press("Enter");

    const sup = page.locator(".citation-ref").first();
    await expect(sup).toBeVisible({ timeout: 10000 });
    await expect(sup).toHaveClass(/citation-ref/);

    const refs = page.locator(".citation-references");
    await expect(refs).toBeVisible({ timeout: 5000 });
    await expect(refs).toContainText("入职手册");
    await expect(refs).toContainText("内部文档");
  });

  test("shows external citation with link and 查看原文", async ({ page }) => {
    await page.route("**/api/agent/internal/chat/stream", (route) => {
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: [
          'data: {"type":"token","content":"参考[1]文章。\\n"}\n',
          'data: {"type":"done","answer":"参考[1]文章。","confidence":0.9,"needs_human":false,"faq_hit":false,"citations":[{"index":1,"title":"微信文章","platform":"wechat","url":"https://mp.weixin.qq.com/s/test","source_name":"公司公众号","is_internal":false}]}\n',
          "data: [DONE]\n",
        ].join("\n"),
      });
    });

    await page.goto("/#/chat/internal");
    await page.waitForLoadState("networkidle");

    const hasToken = await page.evaluate(() => !!localStorage.getItem("token"));
    if (!hasToken) {
      test.skip(true, "Requires auth token");
      return;
    }

    const input = page.locator('textarea[placeholder*="请输入"]');
    await input.fill("test");
    await input.press("Enter");

    const refs = page.locator(".citation-references");
    await expect(refs).toBeVisible({ timeout: 10000 });
    await expect(refs).toContainText("微信文章");
    await expect(refs).toContainText("公司公众号");
    await expect(refs).toContainText("查看原文");

    const link = refs.locator("a.cite-title");
    await expect(link).toHaveAttribute("href", /mp\.weixin\.qq\.com/);
    await expect(link).toHaveAttribute("target", "_blank");
  });

  test("customer chat also renders citations", async ({ page }) => {
    await page.route("**/api/agent/customer/chat/stream", (route) => {
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
        body: [
          'data: {"type":"token","content":"客服参考[1]回答。\\n"}\n',
          'data: {"type":"done","answer":"客服参考[1]回答。","confidence":0.8,"needs_human":false,"faq_hit":false,"citations":[{"index":1,"title":"常见问题","platform":"internal","url":"","source_name":"","is_internal":true}]}\n',
          "data: [DONE]\n",
        ].join("\n"),
      });
    });

    await page.goto("/#/chat/customer");
    await page.waitForLoadState("networkidle");

    const input = page.locator('textarea[placeholder*="请输入"]');
    await expect(input).toBeVisible();

    await input.fill("你好");
    await input.press("Enter");

    const refs = page.locator(".citation-references");
    await expect(refs).toBeVisible({ timeout: 10000 });
    await expect(refs).toContainText("常见问题");
  });
});
