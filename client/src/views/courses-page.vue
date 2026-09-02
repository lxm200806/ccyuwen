<template>
	<section class="card">
		<h2>我的课程</h2>
		<p v-if="courses.length === 0" class="muted">还没有课程，先去「组课」按类型生成一份。</p>
		<article v-for="item in courses" :key="item.id">
			<h3>{{ item.name }}</h3>
			<p class="muted">{{ item.note || '无备注' }} · {{ item.item_count }} 个知识点</p>
			<router-link :to="'/courses/' + item.id + '/drill'">今日默写</router-link>
			&nbsp;
			<router-link :to="'/courses/' + item.id + '/stats'">掌握情况</router-link>
		</article>
		<p v-if="error" class="error">{{ error }}</p>
	</section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { request } from '../api.js'

const courses = ref([])
const error = ref('')

onMounted(async () => {
	try {
		courses.value = await request('/courses')
	} catch (err) {
		error.value = err.message
	}
})
</script>
