<template>
	<section class="card">
		<h2>登录</h2>
		<p v-if="showDemoHint" class="hint">
			本地演示：家长 <code>parent</code> / <code>parent123</code>（已绑孩子 kid），
			学生 <code>kid</code> / <code>kid123</code>，
			管理员 <code>admin</code> / <code>admin123</code>。
			正式环境请改掉默认密码，并关闭演示提示。
		</p>
		<p v-else class="hint">家长登录后可以看孩子今天练得怎么样，帮孩子组课。孩子用自己的账号打开今日默写。</p>
		<form @submit.prevent="handleLogin">
			<label for="name">账号</label>
			<input id="name" v-model="name" autocomplete="username">
			<label for="password">密码</label>
			<input id="password" v-model="password" type="password" autocomplete="current-password">
			<p v-if="error" class="error">{{ error }}</p>
			<button type="submit" :disabled="busy">{{ busy ? '正在登录…' : '进入' }}</button>
		</form>
		<details class="register-box">
			<summary>还没有账号？注册家长或孩子</summary>
			<form @submit.prevent="handleRegister">
				<label for="reg-role">我是</label>
				<select id="reg-role" v-model="regRole">
					<option value="parent">家长</option>
					<option value="user">孩子</option>
				</select>
				<label for="reg-name">账号</label>
				<input id="reg-name" v-model="regName" autocomplete="username">
				<label for="reg-password">密码</label>
				<input id="reg-password" v-model="regPassword" type="password" autocomplete="new-password">
				<p class="hint">家长注册后，用孩子的账号和家庭码绑定。孩子登录后能在课程页看到家庭码。</p>
				<button class="ghost" type="submit" :disabled="busy">注册并进入</button>
			</form>
		</details>
	</section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { request, setSession } from '../api.js'
import { homePath } from '../router.js'

const router = useRouter()
const isDev = import.meta.env.DEV
const showDemoHint = ref(isDev)
const name = ref(isDev ? 'parent' : '')
const password = ref(isDev ? 'parent123' : '')
const error = ref('')
const busy = ref(false)
const regRole = ref('parent')
const regName = ref('')
const regPassword = ref('')

function enter(data) {
	setSession(data.token, data.user)
	router.push(homePath(data.user))
}

async function handleLogin() {
	error.value = ''
	busy.value = true
	try {
		const data = await request('/login', {
			method: 'POST',
			body: JSON.stringify({ name: name.value, password: password.value })
		})
		enter(data)
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function handleRegister() {
	error.value = ''
	busy.value = true
	try {
		const data = await request('/register', {
			method: 'POST',
			body: JSON.stringify({
				name: regName.value,
				password: regPassword.value,
				role: regRole.value
			})
		})
		enter(data)
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
			name.value = 'parent'
			password.value = 'parent123'
		}
	} catch (err) {
		if (!isDev) {
			showDemoHint.value = false
		}
	}
})
</script>
