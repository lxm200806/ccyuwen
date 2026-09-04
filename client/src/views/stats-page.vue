<template>
	<section class="card">
		<h2>课程掌握情况</h2>
		<p v-if="loading" class="muted">正在加载掌握情况…</p>
		<p v-if="error" class="error">{{ error }}</p>
		<p v-else-if="!loading && items.length === 0" class="hint">这门课还没有知识点。请回课程页点「同步新词」，或去「组课」重新生成。</p>
		<table v-if="items.length">
			<thead>
				<tr>
					<th>年级</th>
					<th>知识点</th>
					<th>来源</th>
					<th>学习</th>
					<th>复习</th>
					<th>错误</th>
					<th>间隔</th>
					<th>状态</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="item in items" :key="item.id">
					<td>{{ item.grade || '未分年级' }}</td>
					<td>{{ item.prompt }}</td>
					<td>{{ item.source }}</td>
					<td>{{ item.study_count }}</td>
					<td>{{ item.review_count }}</td>
					<td>{{ item.error_count }}</td>
					<td>{{ item.interval || 0 }} 天</td>
					<td>{{ item.last ? (item.mastered ? '已掌握' : '学习中') : '未学' }}</td>
				</tr>
			</tbody>
		</table>
	</section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api.js'

const route = useRoute()
const items = ref([])
const error = ref('')
const loading = ref(true)

onMounted(async () => {
	loading.value = true
	try {
		const data = await request('/courses/' + route.params.id + '/stats')
		items.value = data.items
	} catch (err) {
		error.value = err.message
	} finally {
		loading.value = false
	}
})
</script>
