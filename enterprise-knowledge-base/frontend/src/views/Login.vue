<template>
  <div class="login-container">
    <el-card class="login-card">
      <h2>企业知识库系统</h2>

      <el-form @submit.prevent>
        <el-form-item>
          <el-input v-model="phone" placeholder="请输入手机号" maxlength="20" />
        </el-form-item>

        <el-form-item>
          <el-input v-model="smsCode" placeholder="请输入验证码" maxlength="6" style="width:60%">
          </el-input>
          <el-button
            :disabled="countdown > 0"
            :loading="sending"
            style="width:38%;margin-left:2%"
            @click="handleSendCode"
          >
            {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
          </el-button>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="loading" style="width:100%" @click="handleSmsLogin">
            登录 / 注册
          </el-button>
        </el-form-item>

        <p class="tip-row">未注册手机号将自动注册并登录</p>
        <p v-if="error" class="error-msg">{{ error }}</p>
        <p v-if="success" class="success-msg">{{ success }}</p>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { sendCode } from "@/api/auth";

const router = useRouter();
const auth = useAuthStore();

const phone = ref("");
const smsCode = ref("");
const loading = ref(false);
const sending = ref(false);
const error = ref("");
const success = ref("");
const countdown = ref(0);
let countdownTimer: ReturnType<typeof setInterval> | null = null;

onUnmounted(() => {
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
});

function startCountdown() {
  countdown.value = 60;
  if (countdownTimer) clearInterval(countdownTimer);
  countdownTimer = setInterval(() => {
    countdown.value--;
    if (countdown.value <= 0 && countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
  }, 1000);
}

async function handleSendCode() {
  if (!phone.value) { error.value = "请输入手机号"; return; }
  sending.value = true;
  error.value = "";
  success.value = "";
  try {
    const resp = await sendCode(phone.value);
    success.value = resp.code ? `验证码: ${resp.code}` : "验证码已发送";
    startCountdown();
  } catch (e: any) {
    const data = e.response?.data;
    const msg = typeof data === "string" ? data : data?.detail;
    error.value = msg || "发送失败";
  } finally {
    sending.value = false;
  }
}

async function handleSmsLogin() {
  if (!phone.value || !smsCode.value) { error.value = "请输入手机号和验证码"; return; }
  loading.value = true;
  error.value = "";
  try {
    await auth.doPhoneLogin(phone.value, smsCode.value);
    router.push("/admin");
  } catch (e: any) {
    error.value = e.response?.data?.detail || "登录失败";
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: #f0f2f5;
}
.login-card {
  width: 420px;
}
h2 {
  text-align: center;
  margin-bottom: 24px;
}
.error-msg {
  color: #f56c6c;
  text-align: center;
}
.success-msg {
  color: #67c23a;
  text-align: center;
}
.tip-row {
  text-align: center;
  color: #909399;
  font-size: 13px;
  margin-top: -8px;
}
</style>
