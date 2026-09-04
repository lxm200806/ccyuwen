<template>
	<section class="card">
		<h2>我的课程</h2>
		<p class="hint">
			先打开一门课做「今日默写」。系统「默认课程」会在词库更新后自动补进新知识点；自己组的课请点「同步新词」，按原来的年级 / 类型筛选补进。也可以去「组课」再生成一份。
		</p>
		<p v-if="loading" class="muted">正在加载课程…</p>
		<p v-else-if="courses.length === 0 && !error" class="hint">
			还没有课程。请先去
			<router-link to="/library">组课</router-link>
			按年级和类型生成一份，或让管理员在「原始资料」同步教材后再刷新。
		</p>
		<p v-if="staleCourses.length" class="banner" role="status">
			词库有更新：{{ staleNames }} 比已发布库少知识点。点「同步新词」按原筛选补进课程。
		</p>
		<article v-for="item in courses" :key="item.id">
			<template v-if="editingId === item.id">
				<label :for="'name-' + item.id">课程名称</label>
				<input :id="'name-' + item.id" v-model="editName">
				<label :for="'note-' + item.id">备注</label>
				<input :id="'note-' + item.id" v-model="editNote">
				<div class="course-actions">
					<button type="button" :disabled="busy" @click="saveEdit(item.id)">保存</button>
					<button class="ghost" type="button" :disabled="busy" @click="cancelEdit">取消</button>
				</div>
			</template>
			<template v-else>
				<h3>{{ item.name }}</h3>
				<p class="muted">
					{{ item.note || '无备注' }} · {{ item.item_count }} 个知识点
					<template v-if="item.kinds && item.kinds.length">
						· {{ kindNames(item.kinds) }} · {{ item.levels.join(' / ') }}
						<template v-if="item.grades && item.grades.length"> · {{ item.grades.join(' / ') }}</template>
					</template>
					· 每天新学 {{ item.newEnergy || 30 }} 能 / 复习 {{ item.reviewEnergy || 30 }} 能
				</p>
				<div class="today-status" :class="(item.progress && item.progress.status) || ''">
					<p class="today-title">{{ progressTitle(item) }}</p>
					<p v-if="progressCheer(item)" class="cheer">{{ progressCheer(item) }}</p>
					<p v-if="item.progress && item.progress.summary" class="hint">{{ item.progress.summary }}</p>
				</div>
				<p v-if="item.pendingCount" class="banner">
					词库有更新，本课还可补进 {{ item.pendingCount }} 条。点「同步新词」按原筛选加入。
				</p>
				<label class="pref-toggle">
					<input
						type="checkbox"
						:checked="!!item.reviewDefaultTest"
						:disabled="busy"
						@change="toggleReviewPref(item, $event.target.checked)"
					>
					到期复习默认用测试模式
				</label>
				<div class="course-actions">
					<router-link :to="'/courses/' + item.id + '/drill'">今日默写</router-link>
					<router-link :to="'/courses/' + item.id + '/plan'">学习计划</router-link>
					<router-link :to="'/courses/' + item.id + '/stats'">掌握情况</router-link>
					<button class="ghost" type="button" :disabled="busy" @click="startEdit(item)">改名</button>
					<button
						class="ghost"
						:class="{ 'sync-needed': item.pendingCount }"
						type="button"
						:disabled="busy"
						@click="syncCourse(item)"
					>同步新词</button>
					<button class="ghost danger" type="button" :disabled="busy" @click="removeCourse(item)">删除</button>
				</div>
			</template>
		</article>
		<p v-if="message" class="ok">{{ message }}</p>
		<p v-if="error" class="error">{{ error }}</p>
	</section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { request } from '../api.js'
import { KIND_LABEL } from '../catalog.js'

function kindNames(ids) {
	return (ids || []).map(function (id) {
		return KIND_LABEL[id] || id
	}).join(' / ')
}

function progressTitle(item) {
	const progress = item.progress || {}
	if (progress.title) {
		return progress.title
	}
	if (progress.status === 'done') {
		return '今天练完了'
	}
	return '今天还没开始练'
}

function progressCheer(item) {
	const progress = item.progress || {}
	const parts = []
	if (progress.todayStreak > 0) {
		parts.push('连续正确 ' + progress.todayStreak)
	}
	if (progress.todayDoneCount > 0) {
		parts.push('今日已完成 ' + progress.todayDoneCount + ' 条')
	} else if (progress.todayPracticed > 0) {
		parts.push('今日已练 ' + progress.todayPracticed + ' 条')
	}
	return parts.join(' · ')
}

const courses = ref([])
const error = ref('')
const message = ref('')
const loading = ref(true)
const busy = ref(false)
const editingId = ref(0)
const editName = ref('')
const editNote = ref('')

const staleCourses = computed(() => courses.value.filter(function (item) {
	return Number(item.pendingCount) > 0
}))
const staleNames = computed(() => staleCourses.value.map(function (item) {
	return item.name
}).join('、'))

async function loadCourses() {
	courses.value = await request('/courses')
}

function startEdit(item) {
	editingId.value = item.id
	editName.value = item.name
	editNote.value = item.note || ''
	error.value = ''
	message.value = ''
}

function cancelEdit() {
	editingId.value = 0
}

async function saveEdit(id) {
	error.value = ''
	message.value = ''
	busy.value = true
	try {
		await request('/courses/' + id, {
			method: 'PATCH',
			body: JSON.stringify({ name: editName.value, note: editNote.value })
		})
		editingId.value = 0
		message.value = '已保存课程名称'
		await loadCourses()
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function toggleReviewPref(item, checked) {
	error.value = ''
	message.value = ''
	busy.value = true
	try {
		const result = await request('/courses/' + item.id, {
			method: 'PATCH',
			body: JSON.stringify({ reviewDefaultTest: !!checked })
		})
		item.reviewDefaultTest = !!result.reviewDefaultTest
		message.value = result.reviewDefaultTest
			? item.name + '：到期复习将默认用测试模式'
			: item.name + '：已改回自动选择模式'
	} catch (err) {
		error.value = err.message
		await loadCourses()
	} finally {
		busy.value = false
	}
}

async function syncCourse(item) {
	error.value = ''
	message.value = ''
	busy.value = true
	try {
		const result = await request('/courses/' + item.id + '/sync', { method: 'POST' })
		message.value = result.added
			? item.name + ' 新补 ' + result.added + ' 条，现共 ' + result.item_count + ' 条'
			: item.name + ' 没有新知识点'
		await loadCourses()
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function removeCourse(item) {
	if (!window.confirm('删除课程「' + item.name + '」？学习记录会一并清掉。')) {
		return
	}
	error.value = ''
	message.value = ''
	busy.value = true
	try {
		await request('/courses/' + item.id, { method: 'DELETE' })
		message.value = '已删除 ' + item.name
		await loadCourses()
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

onMounted(async () => {
	loading.value = true
	try {
		await loadCourses()
	} catch (err) {
		error.value = err.message
	} finally {
		loading.value = false
	}
})
</script>
