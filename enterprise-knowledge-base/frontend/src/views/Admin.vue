<template>
  <div class="admin">
    <el-container>
      <el-header>
        <span>管理后台</span>
        <el-button type="danger" size="small" @click="handleLogout" style="float:right;margin-top:14px">退出</el-button>
      </el-header>
      <el-main>
        <p>欢迎，{{ auth.user?.display_name || auth.user?.username }}</p>
        <p>角色：{{ auth.user?.role }}</p>
        <p>部门：{{ auth.user?.department || '无' }}</p>
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { getMe } from "@/api/auth";

const router = useRouter();
const auth = useAuthStore();

onMounted(async () => {
  if (auth.token && !auth.user) {
    try {
      auth.user = await getMe(auth.token);
    } catch {
      auth.logout();
      router.push("/login");
    }
  }
});

function handleLogout() {
  auth.logout();
  router.push("/login");
}
</script>

<style scoped>
.admin {
  min-height: 100vh;
  background: #f0f2f5;
}
.el-header {
  background: #fff;
  border-bottom: 1px solid #dcdfe6;
  line-height: 60px;
}
</style>
