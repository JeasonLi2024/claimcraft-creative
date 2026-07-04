<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const email = ref('')
const password = ref('')
const passwordConfirm = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function handleSubmit() {
  errorMsg.value = ''
  if (!username.value.trim()) {
    errorMsg.value = '请输入用户名'
    return
  }
  if (!email.value.trim()) {
    errorMsg.value = '请输入邮箱'
    return
  }
  if (!password.value) {
    errorMsg.value = '请输入密码'
    return
  }
  if (password.value !== passwordConfirm.value) {
    errorMsg.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    await authStore.register({
      username: username.value.trim(),
      email: email.value.trim(),
      password: password.value,
    })
    router.push('/cases')
  } catch (e) {
    const detail = e.response?.data
    if (detail && typeof detail === 'object') {
      // DRF 字段错误对象：{ username: [...], email: [...], password: [...] }
      errorMsg.value = Object.entries(detail)
        .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
        .join('；')
    } else if (typeof detail === 'string') {
      errorMsg.value = detail
    } else {
      errorMsg.value = e.response?.data?.error || '注册失败，请稍后重试'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1>注册 ClaimCraft 账号</h1>
      <form class="auth-form" @submit.prevent="handleSubmit">
        <input
          v-model="username"
          type="text"
          placeholder="用户名"
          autocomplete="username"
          :disabled="loading"
        />
        <input
          v-model="email"
          type="email"
          placeholder="邮箱"
          autocomplete="email"
          :disabled="loading"
        />
        <input
          v-model="password"
          type="password"
          placeholder="密码"
          autocomplete="new-password"
          :disabled="loading"
        />
        <input
          v-model="passwordConfirm"
          type="password"
          placeholder="确认密码"
          autocomplete="new-password"
          :disabled="loading"
        />
        <div v-if="errorMsg" class="auth-error">{{ errorMsg }}</div>
        <button type="submit" :disabled="loading">
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>
      <div class="auth-link">
        已有账号？<router-link to="/login">去登录</router-link>
      </div>
    </div>
  </div>
</template>
