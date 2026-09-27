// 把 Vue 用户端 + React 管理后台构建并合并为一份静态产物（frontend/dist）。
// 用法：node scripts/build-static.mjs
// 产物结构：
//   frontend/dist/          -> Vue 用户端（访问 /）
//   frontend/dist/app/      -> React 管理后台（访问 /app/）
import { execSync } from "node:child_process";
import { cpSync, existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const frontendDir = path.join(root, "frontend");
const appDir = path.join(root, "app");

const run = (command, cwd, env) => {
  console.log(`\n> ${command}  (cwd: ${path.relative(root, cwd) || "."})`);
  execSync(command, { cwd, stdio: "inherit", env: { ...process.env, ...env } });
};

// 静态演示构建：默认开启演示模式（假数据），可通过 VITE_DEMO=0 关闭
const demoEnv = { VITE_DEMO: process.env.VITE_DEMO ?? "1" };

run("npm install --no-audit --no-fund", frontendDir);
run("npm run build", frontendDir, demoEnv);

run("npm install --no-audit --no-fund", appDir);
run("npm run build", appDir, demoEnv);

const appDist = path.join(appDir, "dist");
const merged = path.join(frontendDir, "dist", "app");

if (!existsSync(path.join(frontendDir, "dist", "index.html"))) {
  throw new Error("构建失败：未找到 frontend/dist/index.html");
}
if (!existsSync(appDist)) {
  throw new Error("构建失败：未找到 app/dist");
}

rmSync(merged, { recursive: true, force: true });
cpSync(appDist, merged, { recursive: true });

if (!existsSync(path.join(merged, "index.html"))) {
  throw new Error("构建失败：React 管理后台未合并到 frontend/dist/app");
}

console.log(`\n静态产物已就绪：${path.relative(process.cwd(), path.join(frontendDir, "dist"))}`);
