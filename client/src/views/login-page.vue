<template>
	<section class="card">
		<h2>登录</h2>
		<p class="muted">管理员 admin / admin123，学生 kid / kid123</p>
		<form @submit.prevent="handleLogin">
			<label for="name">账号</label>
			<input id="name" v-model="name" autocomplete="username">
			<label for="password">密码</label>
			<input id="password" v-model="password" type="password" autocomplete="current-password">
			<p v-if="error" class="error">{{ error }}</p>
			<button type="submit">进入</button>
		</form>
	</section>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { request, setSession } from '../api.js'

const router = useRouter()
const name = ref('kid')
const password = ref('kid123')
const error = ref('')

async function handleLogin() {
	error.value = ''
	try {
		const data = await request('/login', {
			method: 'POST',
			body: JSON.stringify({ name: name.value, password: password.value })
		})
		setSession(data.token, data.user)
		router.push(data.user.role === 'admin' ? '/admin' : '/courses')
	} catch (err) {
		error.value = err.message
	}
}
</script>
