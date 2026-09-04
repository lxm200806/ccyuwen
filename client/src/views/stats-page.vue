<template>
	<section class="card">
		<h2>{{ courseName }} · 掌握情况</h2>
		<p v-if="loading" class="muted">正在加载掌握情况…</p>
		<p v-if="error" class="error">{{ error }}</p>
		<template v-else-if="!loading">
			<div v-if="today.status === 'empty'" class="hint">
				这门课还没有知识点。请回课程页点「同步新词」，或去「组课」重新生成。
			</div>
			<template v-else>
				<section class="parent-summary">
					<h3>今日情况</h3>
					<p class="today-title" :class="today.status">{{ today.title || '今天还没开始练' }}</p>
					<p class="summary-sentence">{{ summary }}</p>
					<div class="stats">
						<div class="stat">
							<b>{{ today.todayPracticed || 0 }}</b>
							今日已练
						</div>
						<div class="stat">
							<b>{{ accuracyText }}</b>
							正确率
						</div>
						<div class="stat">
							<b>{{ remainingText }}</b>
							还差
						</div>
						<div class="stat">
							<b>{{ mastery.mastered || 0 }}/{{ mastery.total || 0 }}</b>
							已掌握
						</div>
					</div>
					<p v-if="weakText" class="hint">相对容易错：{{ weakText }}</p>
					<p v-if="today.todayDoneCount" class="cheer">今日已完成 {{ today.todayDoneCount }} 条<template v-if="today.todayStreak"> · 连续正确 {{ today.todayStreak }}</template></p>
					<label class="pref-toggle">
						<input
							type="checkbox"
							:checked="reviewDefaultTest"
							:disabled="prefBusy"
							@change="toggleReviewPref($event.target.checked)"
						>
						到期复习默认用测试模式
					</label>
				</section>
				<div class="stats mastery-row">
					<div class="stat">
						<b>{{ mastery.learning || 0 }}</b>
						学习中
					</div>
					<div class="stat">
						<b>{{ mastery.unseen || 0 }}</b>
						还没学
					</div>
				</div>
				<h3>各条掌握</h3>
				<p class="hint">间隔是下次再见到这题大约要隔几天。已掌握大约是隔三周或已连对多次。</p>
				<table v-if="items.length">
					<thead>
						<tr>
							<th>年级</th>
							<th>知识点</th>
							<th>学习</th>
							<th>复习</th>
							<th>错过</th>
							<th>下次</th>
							<th>状态</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="item in items" :key="item.id">
							<td>{{ item.grade || '未分年级' }}</td>
							<td>{{ item.prompt }}</td>
							<td>{{ item.study_count }}</td>
							<td>{{ item.review_count }}</td>
							<td>{{ item.error_count }}</td>
							<td>{{ item.interval || 0 }} 天</td>
							<td>{{ item.last ? (item.mastered ? '已掌握' : '学习中') : '未学' }}</td>
						</tr>
					</tbody>
				</table>
			</template>
		</template>
		<div class="course-actions">
			<router-link :to="'/courses/' + route.params.id + '/drill'">今日默写</router-link>
			<router-link to="/courses">返回课程</router-link>
		</div>
	</section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api.js'

const route = useRoute()
const items = ref([])
const today = ref({})
const mastery = ref({})
const summary = ref('')
const courseName = ref('课程')
const reviewDefaultTest = ref(false)
const error = ref('')
const loading = ref(true)
const prefBusy = ref(false)

const accuracyText = computed(() => {
	if (today.value.todayAccuracy == null) {
		return '—'
	}
	return today.value.todayAccuracy + '%'
})
const remainingText = computed(() => {
	if (today.value.status === 'done') {
		return '练完了'
	}
	const parts = []
	if (today.value.remainingNewEnergy) {
		parts.push('新' + today.value.remainingNewEnergy)
	}
	if (today.value.remainingReviewEnergy) {
		parts.push('复' + today.value.remainingReviewEnergy)
	}
	return parts.join(' / ') || '0 能'
})
const weakText = computed(() => {
	const rows = today.value.weakKinds || mastery.value.weakKinds || []
	return rows.map(function (item) {
		return item.label || item.kind
	}).join('、')
})

async function loadStats() {
	const data = await request('/courses/' + route.params.id + '/stats')
	items.value = data.items || []
	today.value = data.today || {}
	mastery.value = data.mastery || {}
	summary.value = data.summary || (data.today && data.today.summary) || ''
	courseName.value = data.courseName || '课程'
	reviewDefaultTest.value = !!data.reviewDefaultTest
}

async function toggleReviewPref(checked) {
	error.value = ''
	prefBusy.value = true
	try {
		const data = await request('/courses/' + route.params.id, {
			method: 'PATCH',
			body: JSON.stringify({ reviewDefaultTest: !!checked })
		})
		reviewDefaultTest.value = !!data.reviewDefaultTest
	} catch (err) {
		error.value = err.message
		reviewDefaultTest.value = !checked
	} finally {
		prefBusy.value = false
	}
}

onMounted(async () => {
	loading.value = true
	try {
		await loadStats()
	} catch (err) {
		error.value = err.message
	} finally {
		loading.value = false
	}
})
</script>
