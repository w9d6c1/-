<template>
  <div>
    <!-- KPI 卡片 -->
    <el-row :gutter="20" style="margin-bottom: 20px">
      <el-col :span="6">
        <el-card>
          <el-statistic title="今日对话" :value="stats.today_chats" />
          <template #footer><span class="sub-text">内部 + 客服合计</span></template>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="FAQ 命中率" :value="(stats.faq_hit_rate * 100).toFixed(0) + '%'" />
          <template #footer><span class="sub-text">今日问答点击 FAQ 比例</span></template>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="反馈好评率" :value="(stats.feedback_good_rate * 100).toFixed(0) + '%'" />
          <template #footer><span class="sub-text">近 30 天点赞比例</span></template>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card>
          <el-statistic title="待审文档" :value="stats.pending_reviews" />
          <template #footer>
            <el-tag v-if="stats.pending_reviews > 0" type="warning" size="small">{{ stats.pending_reviews }} 份待审核</el-tag>
            <span v-else class="sub-text">无待审</span>
          </template>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势 + 待办 -->
    <el-row :gutter="20">
      <el-col :span="16">
        <el-card>
          <template #header><span>近 7 天对话趋势</span></template>
          <div class="trend-chart">
            <div v-for="d in stats.trend" :key="d.date" class="trend-row">
              <span class="trend-date">{{ d.date }}</span>
              <div class="trend-bar-wrap">
                <div
                  class="trend-bar"
                  :style="{ width: maxCount > 0 ? (d.count / maxCount * 100) + '%' : '0%' }"
                />
                <span class="trend-val">{{ d.count }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header><span>待处理事项</span></template>
          <div class="todo-list">
            <div class="todo-item">
              <el-tag type="warning" size="small">{{ stats.pending_reviews }}</el-tag>
              <span>待审核文档</span>
              <el-button size="small" text @click="$router.push('/admin/review')">去审核 →</el-button>
            </div>
            <div class="todo-item">
              <el-tag type="info" size="small">{{ stats.pending_unanswered }}</el-tag>
              <span>未命中问题</span>
              <el-button size="small" text @click="$router.push('/admin/unanswered')">去处理 →</el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { getToken } from "@/stores/auth";

const BASE = "/api/admin";
function h() { return { Authorization: `Bearer ${getToken()}` }; }

const stats = ref({
  today_chats: 0,
  faq_hit_rate: 0,
  feedback_good_rate: 0,
  pending_reviews: 0,
  pending_unanswered: 0,
  trend: [] as { date: string; count: number }[],
});

const maxCount = computed(() => Math.max(...stats.value.trend.map(d => d.count), 1));

async function loadStats() {
  const resp = await fetch(`${BASE}/dashboard/stats`, { headers: h() });
  if (resp.ok) stats.value = await resp.json();
}

onMounted(loadStats);
</script>

<style scoped>
.sub-text { font-size: 12px; color: #909399; }

.trend-chart { padding: 4px 0; }
.trend-row { display: flex; align-items: center; margin-bottom: 8px; }
.trend-date { width: 44px; font-size: 12px; color: #606266; text-align: right; margin-right: 8px; }
.trend-bar-wrap { flex: 1; background: #f0f2f5; border-radius: 4px; overflow: hidden; display: flex; align-items: center; }
.trend-bar { height: 22px; background: linear-gradient(90deg, #409eff, #66b1ff); border-radius: 4px; min-width: 28px; transition: width 0.3s; }
.trend-val { font-size: 12px; color: #303133; padding-left: 8px; white-space: nowrap; }

.todo-list { display: flex; flex-direction: column; gap: 16px; }
.todo-item { display: flex; align-items: center; gap: 8px; }
</style>
