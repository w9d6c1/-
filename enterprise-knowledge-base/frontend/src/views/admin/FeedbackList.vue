<template>
  <div>
    <el-card class="stats-card">
      <el-row :gutter="20">
        <el-col :span="8"><el-statistic title="总反馈" :value="stats.total" /></el-col>
        <el-col :span="8"><el-statistic title="点赞" :value="stats.likes" /></el-col>
        <el-col :span="8"><el-statistic title="踩" :value="stats.dislikes" /></el-col>
      </el-row>
    </el-card>

    <el-card style="margin-top: 16px">
      <template #header>
        <el-select v-model="filterRating" placeholder="评价筛选" clearable style="width: 140px" @change="fetchList">
          <el-option label="全部" value="" />
          <el-option label="点赞" value="like" />
          <el-option label="踩" value="dislike" />
        </el-select>
      </template>

      <el-table :data="list" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="thread_id" label="会话ID" width="120" />
        <el-table-column prop="rating" label="评价" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.rating === 'like'" type="success">👍 点赞</el-tag>
            <el-tag v-else-if="row.rating === 'dislike'" type="danger">👎 踩</el-tag>
            <el-tag v-else type="info">无评价</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="suggestion" label="建议" min-width="200" show-overflow-tooltip />
        <el-table-column prop="created_at" label="时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { getToken } from "@/stores/auth";

const BASE = "/api/admin";
function h() { return { Authorization: `Bearer ${getToken()}` }; }

const list = ref<any[]>([]);
const stats = ref({ total: 0, likes: 0, dislikes: 0 });
const filterRating = ref("");
const loading = ref(false);

async function fetchList() {
  loading.value = true;
  const params = new URLSearchParams();
  if (filterRating.value) params.set("rating", filterRating.value);
  const resp = await fetch(`${BASE}/feedbacks?${params}`, { headers: h() });
  list.value = await resp.json();
  loading.value = false;
}

async function fetchStats() {
  const resp = await fetch(`${BASE}/feedbacks/stats`, { headers: h() });
  stats.value = await resp.json();
}

onMounted(() => { fetchStats(); fetchList(); });
</script>

<style scoped>
.stats-card { margin-bottom: 0; }
</style>
