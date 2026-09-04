<template>
	<section class="card">
		<h2>{{ title }} · 学习计划</h2>
		<p class="hint">
			每天新学 {{ plan.newEnergy || 30 }} 能量、复习 {{ plan.reviewEnergy || 30 }} 能量。新学能量管还没学过的学习卡，复习能量管到期该复习的卡。按全对估算 SM-2：新学约 {{ plan.newDayCount || 0 }} 天，含复习共 {{ plan.dayCount || 0 }} 天。
			共 {{ plan.pointCount || 0 }} 个知识点、{{ plan.groupCount || 0 }} 张学习卡。点击某一天查看学习卡明细。
		</p>
		<p v-if="loading" class="muted">正在加载学习计划…</p>
		<p v-if="error" class="error">{{ error }}</p>
		<table v-if="plan.days && plan.days.length">
			<thead>
				<tr>
					<th>天数</th>
					<th>安排</th>
					<th>知识点</th>
					<th>能量</th>
				</tr>
			</thead>
			<tbody>
				<template v-for="day in plan.days" :key="day.day">
					<tr class="plan-row" :class="{ open: openDay === day.day }" @click="toggleDay(day.day)">
						<td>第 {{ day.day }} 天</td>
						<td>{{ dayMode(day) }}</td>
						<td>
							<template v-if="day.reviewPointCount && day.newPointCount">
								新 {{ day.newPointCount }} / 复 {{ day.reviewPointCount }}
							</template>
							<template v-else>{{ day.pointCount }}</template>
						</td>
						<td>
							<template v-if="day.reviewEnergy && day.newEnergy">
								新 {{ day.newEnergy }} / 复 {{ day.reviewEnergy }}
							</template>
							<template v-else>{{ day.energy }}</template>
						</td>
					</tr>
					<tr v-if="openDay === day.day" class="plan-detail">
						<td colspan="4">
							<p v-for="(card, index) in day.cards" :key="card.groupKey + '-' + card.role + '-' + index">
								{{ card.role === 'review' ? '复习' : '新学' }} · {{ card.title }}
								<template v-if="card.parts > 1">（{{ card.part }}/{{ card.parts }}）</template>
								<span class="muted"> · {{ kindLabel(card.kind) }} · {{ card.pointCount }} 条 · {{ card.energy }} 能</span>
							</p>
						</td>
					</tr>
				</template>
			</tbody>
		</table>
		<p v-else-if="!loading" class="hint">还没有计划。请确认课程里已有知识点，或回「我的课程」点「同步新词」后再打开本页。</p>
		<div class="course-actions">
			<router-link :to="'/courses/' + route.params.id + '/drill'">今日默写</router-link>
			<router-link to="/courses">返回课程</router-link>
		</div>
	</section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api.js'
import { kindLabel } from '../catalog.js'

const route = useRoute()
const plan = ref({})
const title = ref('课程')
const error = ref('')
const loading = ref(true)
const openDay = ref(0)

function dayMode(day) {
	if (day.mode === 'mixed') {
		return '新学 + 复习'
	}
	if (day.mode === 'review') {
		return '复习'
	}
	return '新学'
}

function toggleDay(day) {
	openDay.value = openDay.value === day ? 0 : day
}

onMounted(async () => {
	loading.value = true
	try {
		const data = await request('/courses/' + route.params.id + '/plan')
		plan.value = data
		title.value = (data.course && data.course.name) || '课程'
	} catch (err) {
		error.value = err.message
	} finally {
		loading.value = false
	}
})
</script>
