<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function handleSubmit() {
  errorMsg.value = ''
  if (!username.value.trim() || !password.value) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    await authStore.login({
      username: username.value.trim(),
      password: password.value,
    })
    router.push('/cases')
  } catch (e) {
    const detail = e.response?.data?.detail
    if (typeof detail === 'string') {
      errorMsg.value = detail
    } else if (detail && typeof detail === 'object') {
      // DRF 字段错误对象
      errorMsg.value = Object.values(detail).flat().join('；')
    } else {
      errorMsg.value = e.response?.data?.error || '登录失败，请检查用户名或密码'
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-card">
      <h1>ClaimCraft 登录</h1>
      <form class="auth-form" @submit.prevent="handleSubmit">
        <input
          v-model="username"
          type="text"
          placeholder="用户名"
          autocomplete="username"
          :disabled="loading"
        />
        <input
          v-model="password"
          type="password"
          placeholder="密码"
          autocomplete="current-password"
          :disabled="loading"
        />
        <div v-if="errorMsg" class="auth-error">{{ errorMsg }}</div>
        <button type="submit" :disabled="loading">
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>
      <div class="auth-link">
        还没有账号？<router-link to="/register">去注册</router-link>
      </div>
    </div>
  </div>
</template>
