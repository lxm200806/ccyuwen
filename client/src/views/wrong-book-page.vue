<template>
	<section class="card">
		<h2>{{ courseName }} · 错题再练</h2>
		<p class="hint">{{ summary }}</p>
		<p v-if="loading" class="muted">正在找出最近容易错的题…</p>
		<p v-if="error" class="error">{{ error }}</p>
		<ul v-if="!loading && items.length" class="wrong-list">
			<li v-for="item in items" :key="item.id">
				<strong>{{ item.kindLabel }}</strong>
				<span>{{ item.prompt }}</span>
				<span class="muted">错过 {{ item.errorCount }} 次</span>
			</li>
		</ul>
		<div class="course-actions">
			<router-link v-if="canDrill && items.length" :to="drillTo">一键再练</router-link>
			<button v-else-if="items.length" class="ghost" type="button" @click="copyHint">让孩子打开错题再练</button>
			<router-link :to="'/courses/' + route.params.id + '/stats'">掌握情况</router-link>
			<router-link :to="backTo">返回</router-link>
		</div>
		<p v-if="message" class="ok">{{ message }}</p>
	</section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getUser, request } from '../api.js'

const route = useRoute()
const items = ref([])
const summary = ref('')
const courseName = ref('课程')
const canDrill = ref(false)
const loading = ref(true)
const error = ref('')
const message = ref('')

const drillTo = computed(() => '/courses/' + route.params.id + '/drill?wrongBook=1&mode=test')
const backTo = computed(() => (getUser() && getUser().role === 'parent') ? '/family' : '/courses')

async function loadWrongBook() {
	const data = await request('/courses/' + route.params.id + '/wrong-book')
	items.value = data.items || []
	summary.value = data.summary || ''
	courseName.value = data.courseName || '课程'
	canDrill.value = !!data.canDrill
}

async function copyHint() {
	const text = '请用孩子账号打开「' + courseName.value + '」的错题再练。'
	try {
		if (navigator.clipboard && navigator.clipboard.writeText) {
			await navigator.clipboard.writeText(text)
		}
	} catch (err) {
		message.value = text
		return
	}
	message.value = '已复制：' + text
}

onMounted(async () => {
	loading.value = true
	try {
		await loadWrongBook()
	} catch (err) {
		error.value = err.message
	} finally {
		loading.value = false
	}
})
</script>
