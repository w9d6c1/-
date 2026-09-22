<template>
  <div class="home">
    <h1>企业知识库系统</h1>
    <p>版本 0.1.0</p>
    <el-space>
      <el-button type="primary" @click="checkHealth">健康检查</el-button>
      <el-button type="success" @click="$router.push('/chat/customer')">客服咨询</el-button>
      <el-button type="primary" @click="$router.push('/chat/internal')">内部问答</el-button>
      <el-button @click="$router.push('/admin')">管理后台</el-button>
    </el-space>
    <p v-if="status" class="status-text">{{ status }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import axios from "axios";

const status = ref("");

async function checkHealth() {
  try {
    const res = await axios.get("/api/health");
    status.value = JSON.stringify(res.data);
  } catch (e: any) {
    status.value = "Error: " + e.message;
  }
}
</script>

<style scoped>
.home { text-align: center; padding-top: 60px; }
.status-text { margin-top: 16px; color: #67c23a; }
</style>
