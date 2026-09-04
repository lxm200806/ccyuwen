<template>
	<section class="card">
		<h2>登录</h2>
		<p v-if="showDemoHint" class="hint">本地演示账号：管理员 <code>admin</code> / <code>admin123</code>，学生 <code>kid</code> / <code>kid123</code>。正式环境请改掉默认密码，并关闭演示提示。</p>
		<p v-else class="hint">请输入账号和密码。没有账号请联系家长或管理员。</p>
		<form @submit.prevent="handleLogin">
			<label for="name">账号</label>
			<input id="name" v-model="name" autocomplete="username">
			<label for="password">密码</label>
			<input id="password" v-model="password" type="password" autocomplete="current-password">
			<p v-if="error" class="error">{{ error }}</p>
			<button type="submit" :disabled="busy">{{ busy ? '正在登录…' : '进入' }}</button>
		</form>
	</section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { request, setSession } from '../api.js'

const router = useRouter()
const isDev = import.meta.env.DEV
const showDemoHint = ref(isDev)
const name = ref(isDev ? 'kid' : '')
const password = ref(isDev ? 'kid123' : '')
const error = ref('')
const busy = ref(false)

async function handleLogin() {
	error.value = ''
	busy.value = true
	try {
		const data = await request('/login', {
			method: 'POST',
			body: JSON.stringify({ name: name.value, password: password.value })
		})
		setSession(data.token, data.user)
		router.push(data.user.role === 'admin' ? '/admin' : '/courses')
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

onMounted(async () => {
	try {
		const meta = await request('/meta')
		const enabled = Boolean(meta.demoHints) || isDev
		showDemoHint.value = enabled
		if (enabled && !name.value) {
			name.value = 'kid'
			password.value = 'kid123'
		}
	} catch (err) {
		if (!isDev) {
			showDemoHint.value = false
		}
	}
})
</script>
