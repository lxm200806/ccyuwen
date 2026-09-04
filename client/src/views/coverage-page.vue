<template>
	<div>
		<p class="hint">看词库里有多少已组进课程、学过、掌握。数字为 0 时，先去「组课」或打开「默认课程」做今日默写。</p>
		<div class="stats">
			<div class="stat"><b>{{ loading ? '…' : (data.total || 0) }}</b>全库</div>
			<div class="stat"><b>{{ loading ? '…' : (data.inCourse || 0) }}</b>已组课</div>
			<div class="stat"><b>{{ loading ? '…' : (data.studied || 0) }}</b>学过</div>
			<div class="stat"><b>{{ loading ? '…' : (data.mastered || 0) }}</b>已掌握</div>
		</div>
		<section class="card">
			<h2>按类型覆盖</h2>
			<p v-if="loading" class="muted">正在加载覆盖情况…</p>
			<p v-if="error" class="error">{{ error }}</p>
			<p v-else-if="!loading && emptyLibrary" class="hint">
				知识库还是空的。管理员请到
				<router-link to="/materials">原始资料</router-link>
				同步教材；学生可先去
				<router-link to="/points">知识点</router-link>
				确认是否已有发布内容。
			</p>
			<p v-else-if="!loading && emptyCourses" class="hint">
				词库里已有 {{ data.total }} 条，但还没有组进任何课程。去
				<router-link to="/library">组课</router-link>
				生成一份，或打开
				<router-link to="/courses">我的课程</router-link>
				里的默认课程开始默写。
			</p>
			<table v-if="!loading && (data.byKind || []).length">
				<thead>
					<tr><th>类型</th><th>总量</th><th>已进课程</th></tr>
				</thead>
				<tbody>
					<tr v-for="row in data.byKind || []" :key="row.kind">
						<td>{{ kindLabel(row.kind) }}</td>
						<td>{{ row.total }}</td>
						<td>{{ row.in_course }}</td>
					</tr>
				</tbody>
			</table>
		</section>
		<section class="card">
			<h2>按年级覆盖</h2>
			<table v-if="!loading && (data.byGrade || []).length">
				<thead>
					<tr><th>年级</th><th>总量</th><th>已进课程</th></tr>
				</thead>
				<tbody>
					<tr v-for="row in data.byGrade || []" :key="row.grade">
						<td>{{ row.grade }}</td>
						<td>{{ row.total }}</td>
						<td>{{ row.in_course }}</td>
					</tr>
				</tbody>
			</table>
			<p v-else-if="!loading && !error" class="muted">还没有按年级的统计。</p>
		</section>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { request } from '../api.js'
import { kindLabel } from '../catalog.js'

const data = ref({})
const error = ref('')
const loading = ref(true)
const emptyLibrary = computed(() => !Number(data.value.total))
const emptyCourses = computed(() => Number(data.value.total) > 0 && !Number(data.value.inCourse))

onMounted(async () => {
	loading.value = true
	try {
		data.value = await request('/library/coverage')
	} catch (err) {
		error.value = err.message
	} finally {
		loading.value = false
	}
})
</script>
