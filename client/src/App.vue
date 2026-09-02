<template>
	<div>
		<header class="topbar">
			<h1>语文培优</h1>
			<button v-if="user" class="ghost" type="button" @click="handleLogout">退出 {{ user.name }}</button>
		</header>
		<nav v-if="user" class="nav">
			<router-link to="/courses">课程</router-link>
			<router-link to="/library">组课</router-link>
			<router-link to="/coverage">覆盖</router-link>
			<router-link v-if="user.role === 'admin'" to="/points">知识点</router-link>
			<router-link v-if="user.role === 'admin'" to="/admin">审核</router-link>
		</nav>
		<router-view />
	</div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { clearSession, getUser } from './api.js'

const router = useRouter()
const user = ref(getUser())

router.afterEach(() => {
	user.value = getUser()
})

function handleLogout() {
	clearSession()
	user.value = null
	router.push({ name: 'Login' })
}
</script>
