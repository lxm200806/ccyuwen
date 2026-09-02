<template>
	<div>
		<div class="stats">
			<div class="stat"><b>{{ data.total || 0 }}</b>全库</div>
			<div class="stat"><b>{{ data.inCourse || 0 }}</b>已组课</div>
			<div class="stat"><b>{{ data.studied || 0 }}</b>学过</div>
			<div class="stat"><b>{{ data.mastered || 0 }}</b>已掌握</div>
		</div>
		<section class="card">
			<h2>按类型覆盖</h2>
			<p v-if="error" class="error">{{ error }}</p>
			<table>
				<thead>
					<tr><th>类型</th><th>总量</th><th>已进课程</th></tr>
				</thead>
				<tbody>
					<tr v-for="row in data.byKind || []" :key="row.kind">
						<td>{{ row.kind }}</td>
						<td>{{ row.total }}</td>
						<td>{{ row.in_course }}</td>
					</tr>
				</tbody>
			</table>
		</section>
	</div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { request } from '../api.js'

const data = ref({})
const error = ref('')

onMounted(async () => {
	try {
		data.value = await request('/library/coverage')
	} catch (err) {
		error.value = err.message
	}
})
</script>
