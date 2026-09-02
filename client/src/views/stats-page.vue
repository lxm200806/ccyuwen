<template>
	<section class="card">
		<h2>课程掌握情况</h2>
		<p v-if="error" class="error">{{ error }}</p>
		<table>
			<thead>
				<tr>
					<th>知识点</th>
					<th>学习</th>
					<th>复习</th>
					<th>错误</th>
					<th>间隔</th>
					<th>状态</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="item in items" :key="item.id">
					<td>{{ item.prompt }}</td>
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

onMounted(async () => {
	try {
		const data = await request('/courses/' + route.params.id + '/stats')
		items.value = data.items
	} catch (err) {
		error.value = err.message
	}
})
</script>
