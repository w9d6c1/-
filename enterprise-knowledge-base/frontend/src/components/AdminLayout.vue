<template>
  <el-container class="layout">
    <el-aside width="200px">
      <el-menu :default-active="route.path" router>
        <el-menu-item index="/admin">控制台</el-menu-item>
        <el-menu-item index="/chat/internal">智能问答</el-menu-item>
        <el-menu-item index="/admin/categories">分类管理</el-menu-item>
        <el-menu-item index="/admin/faqs">FAQ 管理</el-menu-item>
        <el-menu-item index="/admin/documents">文档管理</el-menu-item>
        <el-menu-item index="/admin/source-contents">多源内容</el-menu-item>
        <el-menu-item index="/admin/review" v-if="auth.user?.role === 'superadmin' || auth.user?.role === 'dept_admin'">审核中心</el-menu-item>
        <el-menu-item index="/admin/feedbacks">用户反馈</el-menu-item>
        <el-menu-item index="/admin/unanswered">未命中问题</el-menu-item>
        <el-menu-item index="/admin/dictionary">词库管理</el-menu-item>
        <el-menu-item index="/admin/users" v-if="auth.user?.role === 'superadmin'">用户管理</el-menu-item>
        <el-menu-item index="/admin/permissions" v-if="auth.user?.role === 'superadmin'">权限管理</el-menu-item>
        <el-menu-item index="/admin/audit" v-if="auth.user?.role === 'superadmin'">操作日志</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header>
        <span>{{ auth.user?.display_name || auth.user?.username }}</span>
        <el-tag>{{ auth.user?.role }}</el-tag>
        <el-button size="small" @click="logout">退出</el-button>
      </el-header>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

function logout() {
  auth.logout();
  router.push("/login");
}
</script>

<style scoped>
.layout { min-height: 100vh; }
.el-aside { background: #fff; border-right: 1px solid #ebeef5; }
.el-header { background: #fff; border-bottom: 1px solid #ebeef5; display: flex; align-items: center; gap: 12px; justify-content: flex-end; }
.el-main { background: #f0f2f5; padding: 20px; }
</style>
