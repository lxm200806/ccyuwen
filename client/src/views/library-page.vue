<template>
	<section class="card">
		<h2>从已发布库生成课程</h2>
		<p class="muted">按类型和级别筛选，生成知识点快照。卡片保持短小。</p>
		<label for="course-name">课程名称</label>
		<input id="course-name" v-model="name">
		<label for="course-note">备注</label>
		<input id="course-note" v-model="note">
		<p>类型</p>
		<div class="checks">
			<label v-for="item in kindOptions" :key="item.id">
				<input v-model="kinds" type="checkbox" :value="item.id">
				{{ item.label }}
			</label>
		</div>
		<p>级别</p>
		<div class="checks">
			<label v-for="item in levelOptions" :key="item">
				<input v-model="levels" type="checkbox" :value="item">
				{{ item }}
			</label>
		</div>
		<p class="muted">当前筛选 {{ points.length }} 条</p>
		<button type="button" @click="createCourse">生成课程</button>
		<p v-if="message" class="ok">{{ message }}</p>
		<p v-if="error" class="error">{{ error }}</p>
		<ul>
			<li v-for="point in points" :key="point.id">{{ point.level }} · {{ point.prompt }}</li>
		</ul>
	</section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { request } from '../api.js'

const kindOptions = [
	{ id: 'poem', label: '古诗' },
	{ id: 'idiom', label: '成语' },
	{ id: 'zi', label: '易错字' }
]
const levelOptions = ['L1', 'L2', 'L3', 'L4']
const kinds = ref(['poem', 'idiom', 'zi'])
const levels = ref(['L1', 'L2', 'L3', 'L4'])
const name = ref('默认课程')
const note = ref('系统预置，可按类型再拆')
const points = ref([])
const message = ref('')
const error = ref('')

async function loadLibrary() {
	const all = await request('/library')
	points.value = all.filter(function (item) {
		return kinds.value.includes(item.kind) && levels.value.includes(item.level)
	})
}

async function createCourse() {
	error.value = ''
	message.value = ''
	try {
		const course = await request('/courses', {
			method: 'POST',
			body: JSON.stringify({
				name: name.value,
				note: note.value,
				kinds: kinds.value,
				levels: levels.value
			})
		})
		message.value = '已生成课程 #' + course.id + '，共 ' + course.itemCount + ' 条'
		name.value = '默认课程'
	} catch (err) {
		error.value = err.message
	}
}

watch([kinds, levels], loadLibrary, { deep: true })
onMounted(loadLibrary)
</script>
