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
					<option value="">全部</option>
					<option value="0">未关联资料</option>
					<option v-for="item in officialPacks" :key="item.id" :value="String(item.id)">{{ packLabel(item) }}</option>
				</select>
			</label>
		</div>
		<div class="checks">
			<label>
				<input v-model="byGroup" type="checkbox">
				按组显示
			</label>
		</div>
		<p class="muted">
			共 {{ total }} 条，已显示 {{ points.length }} 条
			<template v-if="byGroup"> · {{ groupedPoints.length }} 组</template>
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
					{{ group.grade || '未分年级' }} · {{ kindLabel(group.kind) }} · {{ group.items.length }} 条 · {{ groupEnergy(group) }} 能 · 组 {{ group.key }}
				</p>
				<article v-for="item in group.items" :key="item.id">
					<p><b>#{{ item.id }}</b> {{ item.level }} · {{ item.prompt }}</p>
					<p class="muted">{{ item.answer }}</p>
					<p v-if="isAdmin" class="muted">编号 {{ item.pointKey || item.point_key || '—' }} · {{ item.energy || 0 }} 能</p>
					<p v-else class="muted">{{ item.energy || 0 }} 能</p>
					<button v-if="isAdmin" class="ghost" type="button" @click="startEdit(item)">编辑</button>
				</article>
			</div>
		</template>
		<template v-else>
			<article v-for="item in points" :key="item.id">
				<p><b>#{{ item.id }}</b> {{ item.grade || '未分年级' }} · {{ item.level }} · {{ kindLabel(item.kind) }}</p>
				<p>{{ item.prompt }}</p>
				<p class="muted">{{ item.answer }}</p>
				<p class="muted">{{ item.source }}{{ item.resourceTitle ? ' · ' + packShort(item.resourceTitle) : '' }}</p>
				<p v-if="isAdmin" class="muted">编号 {{ item.pointKey || item.point_key || '—' }} · 组 {{ item.groupKey || item.group_key || '—' }} · {{ item.energy || 0 }} 能</p>
				<p v-else class="muted">{{ item.energy || 0 }} 能</p>
				<button v-if="isAdmin" class="ghost" type="button" @click="startEdit(item)">编辑</button>
			</article>
		</template>
		<button v-if="points.length < total" class="ghost" type="button" @click="loadMore">加载更多</button>
	</section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getUser, request } from '../api.js'
import { GRADE_OPTIONS, KIND_OPTIONS, LEVEL_OPTIONS, kindLabel } from '../catalog.js'

const isAdmin = (getUser() || {}).role === 'admin'
const intro = isAdmin
	? '已发布库，管理员可改题目和答案。已组课程不会自动改文案；新发布可用课程页「同步新词」补进。'
	: '已发布库，可按年级、类型、册浏览题目和答案。组课页仍不显示答案。'

const kindOptions = KIND_OPTIONS
const levelOptions = LEVEL_OPTIONS
const gradeOptions = GRADE_OPTIONS
const kind = ref('')
const level = ref('')
const grade = ref('')
const resourceId = ref('')
const byGroup = ref(false)
const resources = ref([])
const officialPacks = computed(() => {
	return resources.value.filter((item) => item.isPack).slice().sort((left, right) => packOrder(left.slug) - packOrder(right.slug))
})
const points = ref([])
const total = ref(0)
const editing = ref(null)
const error = ref('')
const message = ref('')

const groupedPoints = computed(() => {
	const groups = []
	const seen = {}
	for (const item of points.value) {
		const key = item.groupKey || item.group_key || String(item.id)
		if (!seen[key]) {
			seen[key] = {
				key,
				kind: item.kind,
				grade: item.grade,
				source: item.source || '',
				items: []
			}
			groups.push(seen[key])
		}
		seen[key].items.push(item)
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

function groupHeading(group) {
	if (group.source) {
		return group.source
	}
	const first = group.items[0]
	return (first && first.prompt) || '未标出处'
}

function groupEnergy(group) {
	return group.items.reduce(function (sum, item) {
		return sum + (Number(item.energy) || 0)
	}, 0)
}

function pageSize() {
	return byGroup.value ? 500 : 100
}

function libraryQuery(offset) {
	const query = ['limit=' + pageSize(), 'offset=' + offset]
	if (kind.value) {
		query.push('kind=' + encodeURIComponent(kind.value))
	}
	if (level.value) {
		query.push('level=' + encodeURIComponent(level.value))
	}
	if (grade.value) {
		query.push('grade=' + encodeURIComponent(grade.value))
	}
	if (resourceId.value !== '') {
		query.push('resourceId=' + encodeURIComponent(resourceId.value))
	}
	query.push('answers=1')
	return '?' + query.join('&')
}

async function loadPoints() {
	error.value = ''
	const data = await request('/library' + libraryQuery(0))
	points.value = data.items || []
	total.value = data.total || 0
}

async function loadMore() {
	error.value = ''
	const data = await request('/library' + libraryQuery(points.value.length))
	points.value = points.value.concat(data.items || [])
	total.value = data.total || total.value
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
		source: item.source || ''
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
				source: editing.value.source
			})
		})
		message.value = '已保存 #' + editing.value.id
		editing.value = null
		await loadPoints()
	} catch (err) {
		error.value = err.message
	}
}

watch([kind, level, grade, resourceId, byGroup], loadPoints)
onMounted(async () => {
	try {
		resources.value = await request('/resources')
	} catch (err) {
		error.value = err.message
	}
	await loadPoints()
})
</script>
