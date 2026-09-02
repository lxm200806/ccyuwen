<template>
	<section class="card">
		<h2>从已发布库生成课程</h2>
		<p class="muted">按年级、类型、级别筛选。每条知识点都带来源，方便对照教材。</p>
		<label for="course-name">课程名称</label>
		<input id="course-name" v-model="name">
		<label for="course-note">备注</label>
		<input id="course-note" v-model="note">
		<p>年级</p>
		<div class="checks">
			<label v-for="item in gradeOptions" :key="item">
				<input v-model="grades" type="checkbox" :value="item">
				{{ item }}
			</label>
		</div>
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
		<div class="row">
			<label>
				每天新学能量
				<input v-model.number="newEnergy" min="8" max="120" type="number">
			</label>
			<label>
				每天复习能量
				<input v-model.number="reviewEnergy" min="8" max="120" type="number">
			</label>
		</div>
		<p class="muted">
			当前筛选 {{ total }} 条。
			<template v-if="preview.dayCount">
				约 {{ preview.groupCount }} 张学习卡、{{ preview.totalEnergy }} 能量；新学约 {{ preview.newDayCount || preview.dayCount }} 天，含复习共 {{ preview.dayCount }} 天（按全对估算）。
			</template>
		</p>
		<p class="muted">字 1 · 词语 2 · 成语 4 · 古诗 16/24/32 · 文言文 24/32/64/96。一张学习卡约 30 能量学一天，15 能量可配两张，50 以上拆成两天。</p>
		<button type="button" @click="createCourse">生成课程</button>
		<p v-if="message" class="ok">{{ message }}</p>
		<p v-if="error" class="error">{{ error }}</p>
		<ul>
			<li v-for="point in points" :key="point.id">
				{{ point.grade || '未分年级' }} · {{ kindLabel(point.kind) }} · {{ point.level }} · {{ point.prompt }}
				<span class="muted"> {{ point.source }} · {{ point.energy || 0 }} 能</span>
			</li>
		</ul>
	</section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { request } from '../api.js'
import { GRADE_OPTIONS, KIND_OPTIONS, LEVEL_OPTIONS, kindLabel } from '../catalog.js'

const kindOptions = KIND_OPTIONS
const levelOptions = LEVEL_OPTIONS
const gradeOptions = GRADE_OPTIONS
const kinds = ref(KIND_OPTIONS.map(function (item) { return item.id }))
const levels = ref(LEVEL_OPTIONS.slice())
const grades = ref(['三年级上'])
const newEnergy = ref(30)
const reviewEnergy = ref(30)
const name = ref('三年级上册默写')
const note = ref('部编三年级上册必背与日积月累')
const points = ref([])
const total = ref(0)
const preview = ref({})
const message = ref('')
const error = ref('')

async function loadLibrary() {
	error.value = ''
	if (!kinds.value.length || !levels.value.length) {
		points.value = []
		total.value = 0
		preview.value = {}
		return
	}
	try {
		const params = new URLSearchParams()
		params.set('kinds', kinds.value.join(','))
		params.set('levels', levels.value.join(','))
		if (grades.value.length) {
			params.set('grades', grades.value.join(','))
		}
		params.set('limit', '500')
		const data = await request('/library?' + params.toString())
		points.value = data.items || []
		total.value = data.total || 0
		preview.value = await request('/courses/preview', {
			method: 'POST',
			body: JSON.stringify({
				kinds: kinds.value,
				levels: levels.value,
				grades: grades.value,
				newEnergy: newEnergy.value,
				reviewEnergy: reviewEnergy.value
			})
		})
	} catch (err) {
		error.value = err.message
	}
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
				levels: levels.value,
				grades: grades.value,
				newEnergy: newEnergy.value,
				reviewEnergy: reviewEnergy.value
			})
		})
		message.value = '已生成课程 #' + course.id + '，共 ' + course.itemCount + ' 条；新学约 ' + ((course.plan && course.plan.newDayCount) || 0) + ' 天，含复习共 ' + ((course.plan && course.plan.dayCount) || 0) + ' 天'
	} catch (err) {
		error.value = err.message
	}
}

watch([kinds, levels, grades, newEnergy, reviewEnergy], loadLibrary, { deep: true })
onMounted(loadLibrary)
</script>
