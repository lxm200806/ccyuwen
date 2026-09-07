<template>
	<section class="card">
		<h2>年级向导组课</h2>
		<p class="hint">先选年级，我们按大约 15 分钟语文给出类型和每天能量。家长会直接给已绑定的孩子组课。</p>
		<label v-if="isParent" for="wizard-student">给哪个孩子</label>
		<select v-if="isParent" id="wizard-student" v-model.number="studentId">
			<option :value="0">请选择孩子</option>
			<option v-for="item in students" :key="item.id" :value="item.id">{{ item.name }}</option>
		</select>
		<label for="wizard-grade">年级</label>
		<select id="wizard-grade" v-model="wizardGrade">
			<option value="">请选择年级</option>
			<option v-for="item in gradeOptions" :key="item" :value="item">{{ item }}</option>
		</select>
		<div v-if="wizardPlan" class="wizard-plan">
			<p class="summary-sentence">{{ wizardPlan.blurb }}</p>
			<p class="muted">
				建议练 {{ wizardPlan.kindLabels.join('、') }} · {{ wizardPlan.levels.join(' / ') }}
				· 每天新学 {{ wizardPlan.newEnergy }} 能 / 复习 {{ wizardPlan.reviewEnergy }} 能
				· 大约 {{ wizardPlan.minutes }} 分钟
			</p>
			<button type="button" :disabled="busy || (isParent && !studentId)" @click="createWizard">
				{{ busy ? '正在生成…' : ('生成「' + wizardPlan.name + '」') }}
			</button>
		</div>
		<p v-if="message" class="ok">{{ message }}</p>
		<p v-if="error" class="error">{{ error }}</p>
	</section>
	<section class="card">
		<h2>自己筛选组课</h2>
		<p class="muted">按年级、类型、级别筛选。同一词条同一题型只收一张卡。组课页不显示答案。</p>
		<label v-if="isParent" for="course-student">给哪个孩子</label>
		<select v-if="isParent" id="course-student" v-model.number="studentId">
			<option :value="0">请选择孩子</option>
			<option v-for="item in students" :key="item.id" :value="item.id">{{ item.name }}</option>
		</select>
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
			<strong>新学能量</strong>是每天新内容的上限，<strong>复习能量</strong>是每天复习到期内容的上限。
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
			当前筛选没有合适的题目。可放宽年级 / 类型 / 级别，或先确认词库是否已同步。
		</p>
		<button type="button" :disabled="busy || loading || total === 0 || (isParent && !studentId)" @click="createCourse">{{ busy ? '正在生成…' : '生成课程' }}</button>
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
import { useRoute } from 'vue-router'
import { getUser, request } from '../api.js'
import { GRADE_OPTIONS, KIND_OPTIONS, LEVEL_OPTIONS, kindLabel, questionTypeLabel } from '../catalog.js'

const route = useRoute()
const user = getUser()
const isParent = !!(user && user.role === 'parent')
const students = ref((user && user.students) || [])
const studentId = ref(Number(route.query.studentId) || 0)
const wizardGrade = ref('三年级上')
const wizardPlan = ref(null)
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

function coursePayload(extra) {
	const body = Object.assign({
		name: name.value,
		note: note.value,
		kinds: kinds.value,
		levels: levels.value,
		grades: grades.value,
		newEnergy: newEnergy.value,
		reviewEnergy: reviewEnergy.value
	}, extra || {})
	if (isParent && studentId.value) {
		body.studentId = studentId.value
	}
	return body
}

async function createCourse() {
	error.value = ''
	message.value = ''
	if (isParent && !studentId.value) {
		error.value = '请先选择孩子'
		return
	}
	busy.value = true
	try {
		const course = await request('/courses', {
			method: 'POST',
			body: JSON.stringify(coursePayload())
		})
		message.value = '已生成「' + course.name + '」，共 ' + course.itemCount + ' 题；新学约 ' + ((course.plan && course.plan.newDayCount) || 0) + ' 天，含复习共 ' + ((course.plan && course.plan.dayCount) || 0) + ' 天'
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function loadWizard() {
	if (!wizardGrade.value) {
		wizardPlan.value = null
		return
	}
	const data = await request('/wizard?grade=' + encodeURIComponent(wizardGrade.value))
	wizardPlan.value = data.plan
	if (data.plan) {
		name.value = data.plan.name
		note.value = data.plan.note
		kinds.value = data.plan.kinds.slice()
		levels.value = data.plan.levels.slice()
		grades.value = [data.plan.grade]
		newEnergy.value = data.plan.newEnergy
		reviewEnergy.value = data.plan.reviewEnergy
	}
}

async function createWizard() {
	error.value = ''
	message.value = ''
	if (isParent && !studentId.value) {
		error.value = '请先选择孩子'
		return
	}
	busy.value = true
	try {
		const course = await request('/courses', {
			method: 'POST',
			body: JSON.stringify(coursePayload({
				wizard: true,
				name: wizardPlan.value.name,
				note: wizardPlan.value.note,
				kinds: wizardPlan.value.kinds,
				levels: wizardPlan.value.levels,
				grades: [wizardPlan.value.grade],
				newEnergy: wizardPlan.value.newEnergy,
				reviewEnergy: wizardPlan.value.reviewEnergy,
				dailyMinutesCap: wizardPlan.value.minutes
			}))
		})
		message.value = '已生成「' + course.name + '」，大约每天 15 分钟。'
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function loadStudents() {
	if (!isParent) {
		return
	}
	const me = await request('/me')
	students.value = me.students || []
	if (!studentId.value && students.value.length === 1) {
		studentId.value = students.value[0].id
	}
}

watch([kinds, levels, grades, newEnergy, reviewEnergy], loadLibrary, { deep: true })
watch(wizardGrade, loadWizard)
onMounted(async () => {
	try {
		await loadStudents()
		await loadWizard()
		await loadLibrary()
	} catch (err) {
		error.value = err.message
	}
})
</script>
