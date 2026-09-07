<template>
	<section class="card">
		<h2>家庭</h2>
		<p class="hint">看孩子今天练得怎么样。默写还是让孩子用自己的账号打开。</p>
		<form class="link-form" @submit.prevent="linkStudent">
			<label for="student-name">孩子账号</label>
			<input id="student-name" v-model="studentName" autocomplete="username">
			<label for="link-code">家庭码</label>
			<input id="link-code" v-model="linkCode" autocomplete="one-time-code">
			<button type="submit" :disabled="busy">绑定孩子</button>
		</form>
		<p v-if="message" class="ok">{{ message }}</p>
		<p v-if="error" class="error">{{ error }}</p>
		<p v-if="loading" class="muted">正在加载家庭情况…</p>
		<p v-else-if="!students.length" class="hint">还没有绑定孩子。问孩子要账号和家庭码，填在上面就能看进度。</p>
		<article v-for="student in students" :key="student.id" class="family-student">
			<h3>{{ student.name }}</h3>
			<div class="today-status" :class="todayClass(student)">
				<p class="today-title">{{ student.today && student.today.title }}</p>
				<p class="hint">{{ student.today && student.today.summary }}</p>
				<p v-if="remainingText(student)" class="cheer">还差 {{ remainingText(student) }}</p>
				<p v-if="weakText(student.today)" class="hint">相对容易错：{{ weakText(student.today) }}</p>
			</div>
			<div v-if="student.week" class="week-brief">
				<h4>近 7 日</h4>
				<p class="summary-sentence">{{ student.week.summary }}</p>
				<div class="stats mastery-row">
					<div class="stat"><b>{{ student.week.daysPracticed || 0 }}</b>练了几天</div>
					<div class="stat"><b>{{ accuracyText(student.week.accuracy) }}</b>平均正确率</div>
				</div>
			</div>
			<article v-for="course in student.courses" :key="course.id" class="family-course">
				<h4>{{ course.name }}</h4>
				<p v-if="course.progress && course.progress.summary" class="hint">{{ course.progress.summary }}</p>
				<label class="pref-toggle">
					<input
						type="checkbox"
						:checked="!!course.reviewDefaultTest"
						:disabled="busy"
						@change="toggleReviewPref(course, $event.target.checked)"
					>
					到期复习默认用测试模式
				</label>
				<label class="pref-toggle minutes-cap">
					今日大约练
					<input
						v-model.number="course.dailyMinutesCap"
						min="0"
						max="180"
						type="number"
						:disabled="busy"
						@change="saveMinutesCap(course)"
					>
					分钟（0 表示不限）
				</label>
				<div class="course-actions">
					<router-link :to="'/courses/' + course.id + '/stats'">掌握情况</router-link>
					<router-link :to="'/courses/' + course.id + '/wrong-book'">错题再练</router-link>
					<router-link :to="'/library?studentId=' + student.id">给孩子组课</router-link>
					<button class="ghost" type="button" @click="copyKidHint(course)">让孩子打开今日默写</button>
				</div>
			</article>
		</article>
	</section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { request } from '../api.js'

const students = ref([])
const studentName = ref('')
const linkCode = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const message = ref('')

function accuracyText(value) {
	return value == null ? '—' : value + '%'
}

function remainingText(student) {
	const today = (student && student.today) || {}
	const parts = []
	if (today.remainingNewEnergy) {
		parts.push('新学 ' + today.remainingNewEnergy + ' 能')
	}
	if (today.remainingReviewEnergy) {
		parts.push('复习 ' + today.remainingReviewEnergy + ' 能')
	}
	return parts.join('、')
}

function weakText(block) {
	return ((block && block.weakKinds) || []).map(function (item) {
		return item.label || item.kind
	}).join('、')
}

function todayClass(student) {
	const title = student && student.today && student.today.title
	if (title === '今天练完了') {
		return 'done'
	}
	return ''
}

async function loadFamily() {
	const data = await request('/family')
	students.value = data.students || []
}

async function linkStudent() {
	error.value = ''
	message.value = ''
	busy.value = true
	try {
		const student = await request('/family/link', {
			method: 'POST',
			body: JSON.stringify({ studentName: studentName.value, linkCode: linkCode.value })
		})
		message.value = '已绑定 ' + student.name
		studentName.value = ''
		linkCode.value = ''
		await loadFamily()
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function toggleReviewPref(course, checked) {
	error.value = ''
	busy.value = true
	try {
		const result = await request('/courses/' + course.id, {
			method: 'PATCH',
			body: JSON.stringify({ reviewDefaultTest: !!checked })
		})
		course.reviewDefaultTest = !!result.reviewDefaultTest
		message.value = course.name + (result.reviewDefaultTest ? '：到期复习将默认用测试模式' : '：已改回自动选择模式')
	} catch (err) {
		error.value = err.message
		await loadFamily()
	} finally {
		busy.value = false
	}
}

async function saveMinutesCap(course) {
	error.value = ''
	busy.value = true
	try {
		const result = await request('/courses/' + course.id, {
			method: 'PATCH',
			body: JSON.stringify({ dailyMinutesCap: Number(course.dailyMinutesCap) || 0 })
		})
		course.dailyMinutesCap = result.dailyMinutesCap || 0
		message.value = course.dailyMinutesCap
			? course.name + '：今天大约练 ' + course.dailyMinutesCap + ' 分钟'
			: course.name + '：已取消今日时长上限'
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function copyKidHint(course) {
	const text = '请用孩子自己的账号登录，打开「' + course.name + '」里的今日默写。'
	try {
		if (navigator.clipboard && navigator.clipboard.writeText) {
			await navigator.clipboard.writeText(text)
			message.value = '已复制给孩子的提示：' + text
			return
		}
	} catch (err) {
		message.value = text
		return
	}
	message.value = text
}

onMounted(async () => {
	loading.value = true
	try {
		await loadFamily()
	} catch (err) {
		error.value = err.message
	} finally {
		loading.value = false
	}
})
</script>
