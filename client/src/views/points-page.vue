<template>
	<section class="card">
		<h2>全部知识点</h2>
		<p class="muted">{{ intro }}</p>
		<div class="row">
			<label>
				类型
				<select v-model="kind">
					<option value="">全部</option>
					<option v-for="item in kindOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
				</select>
			</label>
			<label>
				级别
				<select v-model="level">
					<option value="">全部</option>
					<option v-for="item in levelOptions" :key="item" :value="item">{{ item }}</option>
				</select>
			</label>
		</div>
		<div class="row">
			<label>
				年级
				<select v-model="grade">
					<option value="">全部</option>
					<option v-for="item in gradeOptions" :key="item" :value="item">{{ item }}</option>
				</select>
			</label>
			<label>
				原始资料
				<select v-model="resourceId">
					<option value="all">全部</option>
					<option value="unlinked">未关联资料</option>
					<option v-for="item in officialPacks" :key="item.id" :value="String(item.id)">{{ packLabel(item) }}</option>
				</select>
			</label>
			<label>
				出题
				<select v-model="questionType">
					<option value="">全部</option>
					<option v-for="item in questionTypeOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
				</select>
			</label>
		</div>
		<div class="row">
			<label>
				受众
				<select v-model="audience">
					<option value="">全部</option>
					<option v-for="item in audienceOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
				</select>
			</label>
		</div>
		<div class="checks">
			<label>
				<input v-model="byGroup" type="checkbox">
				按词条
			</label>
		</div>
		<p class="muted">
			<template v-if="loading">正在加载知识点…</template>
			<template v-else>
				词条 {{ entryCount }} · 卡片 {{ total }}
				<template v-if="total">，第 {{ page }} / {{ pageCount }} 页，本页 {{ points.length }} 张</template>
				<template v-if="byGroup"> · {{ groupedPoints.length }} 个词条</template>
			</template>
		</p>
		<p v-if="!loading && !error && total === 0" class="muted">
			{{ emptyHint }}
		</p>
		<p v-if="error" class="error">{{ error }}</p>
		<p v-if="message" class="ok">{{ message }}</p>

		<div v-if="isAdmin && editing" class="card">
			<h3>编辑 #{{ editing.id }}</h3>
			<div class="row">
				<label>
					类型
					<select v-model="editing.kind">
						<option v-for="item in kindOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
					</select>
				</label>
				<label>
					级别
					<select v-model="editing.level">
						<option v-for="item in levelOptions" :key="item" :value="item">{{ item }}</option>
					</select>
				</label>
			</div>
			<label>
				年级
				<select v-model="editing.grade">
					<option value="">未分年级</option>
					<option v-for="item in gradeOptions" :key="item" :value="item">{{ item }}</option>
				</select>
			</label>
			<label for="edit-prompt">提示</label>
			<input id="edit-prompt" v-model="editing.prompt">
			<label for="edit-answer">答案</label>
			<textarea id="edit-answer" v-model="editing.answer"></textarea>
			<div class="row">
				<label>
					出题
					<select v-model="editing.questionType">
						<option v-for="item in questionTypeOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
					</select>
				</label>
				<label>
					受众
					<select v-model="editing.audience">
						<option v-for="item in audienceOptions" :key="item.id" :value="item.id">{{ item.label }}</option>
					</select>
				</label>
			</div>
			<label for="edit-lemma">词条</label>
			<input id="edit-lemma" v-model="editing.lemma">
			<label for="edit-options">选项 JSON</label>
			<textarea id="edit-options" v-model="editing.options"></textarea>
			<label for="edit-tags">标签</label>
			<input id="edit-tags" v-model="editing.tags">
			<label for="edit-source">出处</label>
			<input id="edit-source" v-model="editing.source">
			<button type="button" @click="savePoint">保存</button>
			<button class="ghost" type="button" @click="editing = null">取消</button>
		</div>

		<template v-if="byGroup">
			<div v-for="group in groupedPoints" :key="group.key" class="point-group">
				<h3>{{ groupHeading(group) }}</h3>
				<p class="muted">
					{{ groupMeta(group) }} · {{ group.items.length }} 张卡 · {{ groupEnergy(group) }} 能 · {{ group.key }}
				</p>
				<article v-for="item in group.items" :key="item.id">
					<p><b>#{{ item.id }}</b> {{ item.level }} · {{ questionTypeLabel(item.questionType || item.question_type) }} · {{ item.prompt }}</p>
					<p class="muted">{{ item.answer }}</p>
					<p v-if="isAdmin" class="muted">编号 {{ item.pointKey || item.point_key || '—' }} · {{ audienceLabel(item.audience) }} · {{ item.energy || 0 }} 能</p>
					<p v-else class="muted">{{ audienceLabel(item.audience) }} · {{ item.energy || 0 }} 能</p>
					<button v-if="isAdmin" class="ghost" type="button" @click="startEdit(item)">编辑</button>
				</article>
			</div>
		</template>
		<template v-else>
			<article v-for="item in points" :key="item.id">
				<p><b>#{{ item.id }}</b> {{ item.grade || '未分年级' }} · {{ item.level }} · {{ kindLabel(item.kind) }} · {{ questionTypeLabel(item.questionType || item.question_type) }}</p>
				<p>{{ item.prompt }}</p>
				<p class="muted">{{ item.answer }}</p>
				<p class="muted">{{ item.source }}{{ item.resourceTitle ? ' · ' + packShort(item.resourceTitle) : '' }}</p>
				<p v-if="isAdmin" class="muted">编号 {{ item.pointKey || item.point_key || '—' }} · 词条 {{ item.entryKey || item.entry_key || item.groupKey || item.group_key || '—' }} · {{ audienceLabel(item.audience) }} · {{ item.energy || 0 }} 能</p>
				<p v-else class="muted">{{ audienceLabel(item.audience) }} · {{ item.energy || 0 }} 能</p>
				<button v-if="isAdmin" class="ghost" type="button" @click="startEdit(item)">编辑</button>
			</article>
		</template>
		<Pager :page="page" :page-count="pageCount" @update:page="goPage" />
	</section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getUser, request } from '../api.js'
import { AUDIENCE_OPTIONS, GRADE_OPTIONS, KIND_OPTIONS, LEVEL_OPTIONS, QUESTION_TYPE_OPTIONS, audienceLabel, kindLabel, questionTypeLabel } from '../catalog.js'
import Pager from '../pager.vue'

const isAdmin = (getUser() || {}).role === 'admin'
const intro = isAdmin
	? '已发布库，管理员可改题目和答案。各册教材可以重复收录同一成语；全局词条不重复，但可以同时属于多个年级。计数按词条，练习按卡片。已组课程不会自动改文案；新发布可用课程页「同步新词」补进。系统「默认课程」会自动补齐。'
	: '已发布库，可按年级、类型、册、出题方式浏览。这里按「这一册的卡片」筛选；组课会按全局词条的年级收录，同一词条一门课里不重复。'

const kindOptions = KIND_OPTIONS
const levelOptions = LEVEL_OPTIONS
const gradeOptions = GRADE_OPTIONS
const questionTypeOptions = QUESTION_TYPE_OPTIONS
const audienceOptions = AUDIENCE_OPTIONS
const kind = ref('')
const level = ref('')
const grade = ref('')
const resourceId = ref('all')
const questionType = ref('')
const audience = ref('')
const byGroup = ref(false)
const loading = ref(true)
let loadTicket = 0
const resources = ref([])
const officialPacks = computed(() => {
	return resources.value.filter((item) => item.isPack).slice().sort((left, right) => packOrder(left.slug) - packOrder(right.slug))
})
const points = ref([])
const total = ref(0)
const entryCount = ref(0)
const page = ref(1)
const PAGE_SIZE = 50
const pageCount = computed(() => Math.max(1, Math.ceil((Number(total.value) || 0) / PAGE_SIZE)))
const editing = ref(null)
const error = ref('')
const message = ref('')

const groupedPoints = computed(() => {
	const groups = []
	const seen = {}
	for (const item of points.value) {
		const key = item.entryKey || item.entry_key || item.groupKey || item.group_key || String(item.id)
		if (!seen[key]) {
			seen[key] = {
				key,
				kind: item.kind,
				grade: item.grade,
				grades: item.entryGrades || item.entry_grades || item.grade || '',
				levels: item.entryLevels || item.entry_levels || item.level || '',
				source: item.source || '',
				lemma: item.lemma || '',
				items: []
			}
			groups.push(seen[key])
		}
		seen[key].items.push(item)
		if (item.entryGrades || item.entry_grades) {
			seen[key].grades = item.entryGrades || item.entry_grades
		}
		if (item.entryLevels || item.entry_levels) {
			seen[key].levels = item.entryLevels || item.entry_levels
		}
	}
	return groups
})

function packOrder(slug) {
	const matched = /^grade(\d+)-(shang|xia)$/.exec(slug || '')
	if (!matched) {
		return 999
	}
	return Number(matched[1]) * 2 + (matched[2] === 'xia' ? 1 : 0)
}

function packLabel(item) {
	return packShort(item.title || item.filename || ('#' + item.id))
}

function packShort(title) {
	return String(title || '').split('｜')[0]
}

function formatLabels(text, empty) {
	const items = String(text || '').split(/[;；,，]/).map((item) => item.trim()).filter(Boolean)
	return items.join('、') || empty || ''
}

function groupMeta(group) {
	const parts = [formatLabels(group.grades || group.grade, '未分年级')]
	const levels = formatLabels(group.levels, '')
	if (levels) {
		parts.push(levels)
	}
	parts.push(kindLabel(group.kind))
	return parts.join(' · ')
}

function groupHeading(group) {
	if (group.lemma) {
		return group.lemma
	}
	if (group.source) {
		return group.source
	}
	const first = group.items[0]
	return (first && (first.lemma || first.prompt)) || '未标词条'
}

function groupEnergy(group) {
	return group.items.reduce(function (sum, item) {
		return sum + (Number(item.energy) || 0)
	}, 0)
}

function libraryQuery(offset) {
	const query = ['limit=' + PAGE_SIZE, 'offset=' + offset]
	if (kind.value) {
		query.push('kind=' + encodeURIComponent(kind.value))
	}
	if (level.value) {
		query.push('level=' + encodeURIComponent(level.value))
	}
	if (grade.value) {
		query.push('grade=' + encodeURIComponent(grade.value))
	}
	const resource = String(resourceId.value || 'all')
	if (resource === 'unlinked') {
		query.push('resourceId=unlinked')
	} else if (/^[1-9]\d*$/.test(resource)) {
		query.push('resourceId=' + resource)
	}
	if (questionType.value) {
		query.push('questionType=' + encodeURIComponent(questionType.value))
	}
	if (audience.value) {
		query.push('audience=' + encodeURIComponent(audience.value))
	}
	query.push('answers=1')
	return '?' + query.join('&')
}

const emptyHint = computed(() => {
	if (resourceId.value === 'unlinked') {
		return '没有未关联教材的知识点。系统预置词库都已挂到各册，请把「原始资料」改回「全部」。'
	}
	if (kind.value || level.value || grade.value || questionType.value || audience.value || /^[1-9]\d*$/.test(String(resourceId.value || ''))) {
		return '没有符合当前筛选的已发布知识点。可清空类型、级别、年级或册后再看。'
	}
	return '知识库还是空的。管理员请到「原始资料」同步教材；学生可先打开「我的课程」看默认课是否已有内容，或请家长联系管理员。'
})

async function loadPoints() {
	const ticket = ++loadTicket
	error.value = ''
	loading.value = true
	try {
		let data = await request('/library' + libraryQuery((page.value - 1) * PAGE_SIZE))
		if (ticket !== loadTicket) {
			return
		}
		total.value = Number(data.total) || 0
		entryCount.value = Number(data.entryCount) || total.value
		const pages = Math.max(1, Math.ceil(total.value / PAGE_SIZE))
		if (page.value > pages) {
			page.value = pages
			data = await request('/library' + libraryQuery((page.value - 1) * PAGE_SIZE))
			if (ticket !== loadTicket) {
				return
			}
			total.value = Number(data.total) || 0
			entryCount.value = Number(data.entryCount) || total.value
		}
		points.value = data.items || []
	} catch (err) {
		if (ticket !== loadTicket) {
			return
		}
		error.value = err.message
		points.value = []
		total.value = 0
		entryCount.value = 0
	} finally {
		if (ticket === loadTicket) {
			loading.value = false
		}
	}
}

function goPage(next) {
	page.value = next
	loadPoints()
}

function encodeOptionsText(value) {
	if (!value) {
		return ''
	}
	if (typeof value === 'string') {
		return value
	}
	try {
		return JSON.stringify(value, null, 2)
	} catch (err) {
		return ''
	}
}

function startEdit(item) {
	editing.value = {
		id: item.id,
		kind: item.kind,
		level: item.level,
		grade: item.grade || '',
		prompt: item.prompt,
		answer: item.answer || '',
		tags: item.tags || '',
		source: item.source || '',
		questionType: item.questionType || item.question_type || 'dictation',
		audience: item.audience || 'all',
		lemma: item.lemma || '',
		options: encodeOptionsText(item.options)
	}
	message.value = ''
}

async function savePoint() {
	error.value = ''
	message.value = ''
	try {
		await request('/library/' + editing.value.id, {
			method: 'PATCH',
			body: JSON.stringify({
				kind: editing.value.kind,
				level: editing.value.level,
				grade: editing.value.grade,
				prompt: editing.value.prompt,
				answer: editing.value.answer,
				tags: editing.value.tags,
				source: editing.value.source,
				questionType: editing.value.questionType,
				audience: editing.value.audience,
				lemma: editing.value.lemma,
				options: editing.value.options
			})
		})
		message.value = '已保存 #' + editing.value.id
		editing.value = null
		await loadPoints()
	} catch (err) {
		error.value = err.message
	}
}

watch([kind, level, grade, resourceId, questionType, audience, byGroup], () => {
	page.value = 1
	loadPoints()
})

async function loadResources() {
	try {
		resources.value = await request('/resources')
	} catch (err) {
		if (!error.value) {
			error.value = err.message
		}
	}
}

onMounted(() => {
	loadResources()
	loadPoints()
})
</script>
