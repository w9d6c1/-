import { createRouter, createWebHashHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "home", component: () => import("@/views/Home.vue") },
    { path: "/login", name: "login", component: () => import("@/views/Login.vue") },
    {
      path: "/chat/internal",
      name: "internalChat",
      component: () => import("@/views/InternalChat.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/chat/customer",
      name: "customerChat",
      component: () => import("@/views/CustomerChat.vue"),
    },
    {
      path: "/admin",
      component: () => import("@/components/AdminLayout.vue"),
      meta: { requiresAuth: true },
      children: [
        { path: "", name: "dashboard", component: () => import("@/views/admin/Dashboard.vue") },
        { path: "categories", name: "categories", component: () => import("@/views/admin/CategoryList.vue") },
        { path: "faqs", name: "faqs", component: () => import("@/views/admin/FaqList.vue") },
        { path: "documents", name: "documents", component: () => import("@/views/admin/DocumentList.vue") },
        { path: "source-contents", name: "sourceContents", component: () => import("@/views/admin/SourceContentList.vue") },
        { path: "review", name: "review", component: () => import("@/views/admin/ReviewCenter.vue") },
        { path: "feedbacks", name: "feedbacks", component: () => import("@/views/admin/FeedbackList.vue") },
        { path: "unanswered", name: "unanswered", component: () => import("@/views/admin/UnansweredList.vue") },
        { path: "dictionary", name: "dictionary", component: () => import("@/views/admin/DictionaryList.vue") },
        { path: "permissions", name: "permissions", component: () => import("@/views/admin/PermissionList.vue") },
        { path: "audit", name: "audit", component: () => import("@/views/admin/AuditLog.vue") },
        { path: "users", name: "users", component: () => import("@/views/admin/UserList.vue") },
      ],
    },
  ],
});

let authInitialized = false;

function readToken(): string {
  try {
    return localStorage.getItem("token") || "";
  } catch {
    return "";
  }
}

router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore();
  if (!authInitialized) {
    authInitialized = true;
    if (readToken()) {
      try {
        await auth.init();
      } catch {
        // init 内部已处理 logout
      }
    }
  }

  const token = readToken() || auth.token;
  if (to.meta.requiresAuth && !token) {
    next("/login");
  } else {
    next();
  }
});

export default router;
