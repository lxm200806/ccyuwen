<template>
	<section class="card">
		<h2>我的课程</h2>
		<p class="muted">组课后可改名、删课。词库有新发布时，点「同步新词」按原筛选补进课程。</p>
		<p v-if="courses.length === 0" class="muted">还没有课程，先去「组课」按类型生成一份。</p>
		<article v-for="item in courses" :key="item.id">
			<template v-if="editingId === item.id">
				<label :for="'name-' + item.id">课程名称</label>
				<input :id="'name-' + item.id" v-model="editName">
				<label :for="'note-' + item.id">备注</label>
				<input :id="'note-' + item.id" v-model="editNote">
				<div class="course-actions">
					<button type="button" @click="saveEdit(item.id)">保存</button>
					<button class="ghost" type="button" @click="cancelEdit">取消</button>
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
				<div class="course-actions">
					<router-link :to="'/courses/' + item.id + '/drill'">今日默写</router-link>
					<router-link :to="'/courses/' + item.id + '/plan'">学习计划</router-link>
					<router-link :to="'/courses/' + item.id + '/stats'">掌握情况</router-link>
					<button class="ghost" type="button" @click="startEdit(item)">改名</button>
					<button class="ghost" type="button" @click="syncCourse(item)">同步新词</button>
					<button class="ghost danger" type="button" @click="removeCourse(item)">删除</button>
				</div>
			</template>
		</article>
		<p v-if="message" class="ok">{{ message }}</p>
		<p v-if="error" class="error">{{ error }}</p>
	</section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { request } from '../api.js'
import { KIND_LABEL } from '../catalog.js'

function kindNames(ids) {
	return (ids || []).map(function (id) {
		return KIND_LABEL[id] || id
	}).join(' / ')
}

const courses = ref([])
const error = ref('')
const message = ref('')
const editingId = ref(0)
const editName = ref('')
const editNote = ref('')

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
	}
}

async function syncCourse(item) {
	error.value = ''
	message.value = ''
	try {
		const result = await request('/courses/' + item.id + '/sync', { method: 'POST' })
		message.value = result.added
			? item.name + ' 新补 ' + result.added + ' 条，现共 ' + result.item_count + ' 条'
			: item.name + ' 没有新知识点'
		await loadCourses()
	} catch (err) {
		error.value = err.message
	}
}

async function removeCourse(item) {
	if (!window.confirm('删除课程「' + item.name + '」？学习记录会一并清掉。')) {
		return
	}
	error.value = ''
	message.value = ''
	try {
		await request('/courses/' + item.id, { method: 'DELETE' })
		message.value = '已删除 ' + item.name
		await loadCourses()
	} catch (err) {
		error.value = err.message
	}
}

onMounted(async () => {
	try {
		await loadCourses()
	} catch (err) {
		error.value = err.message
	}
})
</script>
