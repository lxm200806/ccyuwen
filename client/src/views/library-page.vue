<template>
	<section class="card">
		<h2>从已发布库生成课程</h2>
		<p class="muted">按年级、类型、级别筛选。教材和小学成语里允许重复；组课时同一词条同一题型只收一张卡。若这个成语既属一年级又属二年级，两门课里都会出现，可以再学一遍。组课页不显示答案；要看答案请去「知识点」。</p>
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
		<p class="hint">
			<strong>新学能量</strong>是每天新内容的上限，<strong>复习能量</strong>是每天复习到期内容的上限。一张<strong>学习卡</strong>是同一课文 / 模块的几条知识点，能量加总后按天安排。
		</p>
		<p class="muted">
			<template v-if="loading">正在按当前筛选预览…</template>
			<template v-else>
				当前筛选 {{ entryCount }} 个词条、{{ total }} 张卡片。
				<template v-if="preview.dayCount">
					约 {{ preview.groupCount }} 张学习卡、{{ preview.totalEnergy }} 能量；新学约 {{ preview.newDayCount || preview.dayCount }} 天，含复习共 {{ preview.dayCount }} 天（按全对估算）。
				</template>
			</template>
		</p>
		<p v-if="!loading && total === 0" class="hint">
			当前筛选没有已发布知识点。可放宽年级 / 类型 / 级别，或先去「知识点」确认词库，管理员也可在「原始资料」同步教材。
		</p>
		<p class="muted">字 1 · 词语 2 · 成语 4 · 古诗 16/24/32 · 文言文 24/32/64/96。一张学习卡约 30 能量学一天，15 能量可配两张，50 以上拆成两天。</p>
		<button type="button" :disabled="busy || loading || total === 0" @click="createCourse">{{ busy ? '正在生成…' : '生成课程' }}</button>
		<p v-if="message" class="ok">{{ message }}</p>
		<p v-if="error" class="error">{{ error }}</p>
		<ul>
			<li v-for="point in points" :key="point.id">
				{{ point.entryGrades || point.grade || '未分年级' }} · {{ kindLabel(point.kind) }} · {{ questionTypeLabel(point.questionType || point.question_type) }} · {{ point.level }} · {{ point.lemma || point.prompt }}
				<span class="muted"> {{ point.source }} · {{ point.energy || 0 }} 能</span>
			</li>
		</ul>
	</section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { request } from '../api.js'
import { GRADE_OPTIONS, KIND_OPTIONS, LEVEL_OPTIONS, kindLabel, questionTypeLabel } from '../catalog.js'

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
const entryCount = ref(0)
const preview = ref({})
const message = ref('')
const error = ref('')
const loading = ref(false)
const busy = ref(false)
let loadTicket = 0

async function loadLibrary() {
	error.value = ''
	if (!kinds.value.length || !levels.value.length) {
		points.value = []
		total.value = 0
		entryCount.value = 0
		preview.value = {}
		return
	}
	const ticket = ++loadTicket
	const selectedKinds = kinds.value.slice()
	const selectedLevels = levels.value.slice()
	const selectedGrades = grades.value.slice()
	const selectedNew = newEnergy.value
	const selectedReview = reviewEnergy.value
	loading.value = true
	try {
		const params = new URLSearchParams()
		params.set('kinds', selectedKinds.join(','))
		params.set('levels', selectedLevels.join(','))
		if (selectedGrades.length) {
			params.set('grades', selectedGrades.join(','))
		}
		params.set('limit', '500')
		const data = await request('/library?' + params.toString())
		if (ticket !== loadTicket) {
			return
		}
		points.value = data.items || []
		total.value = data.total || 0
		entryCount.value = data.entryCount || data.total || 0
		preview.value = await request('/courses/preview', {
			method: 'POST',
			body: JSON.stringify({
				kinds: selectedKinds,
				levels: selectedLevels,
				grades: selectedGrades,
				newEnergy: selectedNew,
				reviewEnergy: selectedReview
			})
		})
		if (ticket !== loadTicket) {
			return
		}
	} catch (err) {
		if (ticket !== loadTicket) {
			return
		}
		error.value = err.message
	} finally {
		if (ticket === loadTicket) {
			loading.value = false
		}
	}
}

async function createCourse() {
	error.value = ''
	message.value = ''
	busy.value = true
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
	} finally {
		busy.value = false
	}
}

watch([kinds, levels, grades, newEnergy, reviewEnergy], loadLibrary, { deep: true })
onMounted(loadLibrary)
</script>
