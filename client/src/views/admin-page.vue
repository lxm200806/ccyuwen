<template>
	<div>
		<section class="card">
			<h2>抽取到草稿库</h2>
			<p class="hint">可先在「原始资料」里点「用作抽取」，把资源 ID 带到这里。粘贴 CSV / JSON 后写入的条目，才会进入下面的审核队列。</p>
			<label for="resource-id">关联资源 ID（可选）</label>
			<input id="resource-id" v-model="resourceId" placeholder="上传后的 id">
			<label for="import-text">CSV 或 JSON</label>
			<textarea id="import-text" v-model="importText" placeholder='kind,level,grade,prompt,answer,tags,source'></textarea>
			<button type="button" :disabled="busy" @click="importDrafts">{{ busy ? '正在写入…' : '写入草稿' }}</button>
			<p v-if="message" class="ok">{{ message }}</p>
			<p v-if="error" class="error">{{ error }}</p>
		</section>

		<section class="card">
			<h2>草稿审核</h2>
			<p v-if="loading" class="muted">正在加载草稿…</p>
			<div v-else-if="total === 0" class="hint">
				<p>暂无待审草稿。</p>
				<p>
					系统预置的十二册教材和「小学成语」在「原始资料」里同步后，会<strong>直接写入已发布库</strong>，不会出现在这个草稿队列。要更新这些内容，请打开
					<router-link to="/materials">原始资料</router-link>
					做增量同步或单册同步。只有在本页粘贴 CSV / JSON「写入草稿」的条目，才需要在这里审核发布。
				</p>
			</div>
			<template v-else>
				<p class="muted">待审 {{ total }} 条，第 {{ page }} / {{ pageCount }} 页</p>
				<div class="batch-bar">
					<label class="pref-toggle">
						<input
							type="checkbox"
							:checked="allPageSelected"
							:indeterminate="partialPageSelected"
							@change="toggleSelectPage"
						>
						全选本页
					</label>
					<button type="button" :disabled="busy || selectedIds.length === 0" @click="publishSelected">
						发布选中（{{ selectedIds.length }}）
					</button>
					<button class="ghost" type="button" :disabled="busy || selectedIds.length === 0" @click="selectedIds = []">
						取消选择
					</button>
				</div>
				<article v-for="item in drafts" :key="item.id" class="lib-item">
					<label class="lib-pick">
						<input type="checkbox" :checked="isSelected(item.id)" @change="toggleOne(item.id, $event.target.checked)">
						<div class="lib-body">
							<p><b>#{{ item.id }}</b> {{ item.grade || '未分年级' }} · {{ item.kind }} / {{ item.level }}</p>
							<p>{{ item.prompt }}</p>
							<p class="muted">{{ item.answer }}</p>
						</div>
					</label>
					<div class="course-actions">
						<button type="button" :disabled="busy" @click="publish(item.id)">发布</button>
						<button class="ghost" type="button" :disabled="busy" @click="discard(item.id)">弃用</button>
					</div>
				</article>
				<Pager :page="page" :page-count="pageCount" @update:page="goPage" />
			</template>
		</section>
	</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api.js'
import Pager from '../pager.vue'

const PAGE_SIZE = 20
const route = useRoute()
const resourceId = ref('')
const importText = ref('')
const drafts = ref([])
const total = ref(0)
const page = ref(1)
const selectedIds = ref([])
const message = ref('')
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const pageCount = computed(() => Math.max(1, Math.ceil((Number(total.value) || 0) / PAGE_SIZE)))
const allPageSelected = computed(() => {
	return drafts.value.length > 0 && drafts.value.every((item) => selectedIds.value.includes(item.id))
})
const partialPageSelected = computed(() => {
	return drafts.value.some((item) => selectedIds.value.includes(item.id)) && !allPageSelected.value
})

function applyResourceQuery() {
	if (route.query.resourceId) {
		resourceId.value = String(route.query.resourceId)
	}
}

function isSelected(id) {
	return selectedIds.value.includes(id)
}

function toggleOne(id, checked) {
	if (checked) {
		if (!selectedIds.value.includes(id)) {
			selectedIds.value = selectedIds.value.concat(id)
		}
		return
	}
	selectedIds.value = selectedIds.value.filter((item) => item !== id)
}

function toggleSelectPage(event) {
	const ids = drafts.value.map((item) => item.id)
	if (event.target.checked) {
		selectedIds.value = selectedIds.value.concat(ids.filter((id) => !selectedIds.value.includes(id)))
		return
	}
	selectedIds.value = selectedIds.value.filter((id) => !ids.includes(id))
}

function dropSelected(ids) {
	const gone = new Set(ids)
	selectedIds.value = selectedIds.value.filter((id) => !gone.has(id))
}

async function loadDrafts() {
	let data = await request('/drafts?status=draft&limit=' + PAGE_SIZE + '&offset=' + ((page.value - 1) * PAGE_SIZE))
	total.value = Number(data.total) || 0
	const pages = Math.max(1, Math.ceil(total.value / PAGE_SIZE))
	if (page.value > pages) {
		page.value = pages
		data = await request('/drafts?status=draft&limit=' + PAGE_SIZE + '&offset=' + ((page.value - 1) * PAGE_SIZE))
		total.value = Number(data.total) || 0
	}
	drafts.value = data.items || []
}

function goPage(next) {
	page.value = next
	reloadList()
}

async function reloadList() {
	error.value = ''
	try {
		await loadDrafts()
	} catch (err) {
		error.value = err.message
	}
}

async function importDrafts() {
	error.value = ''
	message.value = ''
	busy.value = true
	try {
		const payload = { text: importText.value }
		if (resourceId.value) {
			payload.resourceId = Number(resourceId.value)
		}
		const result = await request('/drafts/import', {
			method: 'POST',
			body: JSON.stringify(payload)
		})
		message.value = '写入 ' + result.ok + ' 条，跳过 ' + result.skip
		importText.value = ''
		page.value = 1
		await loadDrafts()
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function publish(id) {
	error.value = ''
	busy.value = true
	try {
		await request('/drafts/' + id + '/publish', { method: 'POST' })
		message.value = '已发布 #' + id + '，系统默认课程会自动补进'
		dropSelected([id])
		await loadDrafts()
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function publishSelected() {
	error.value = ''
	if (selectedIds.value.length === 0) {
		error.value = '请先勾选要发布的草稿'
		return
	}
	busy.value = true
	try {
		const result = await request('/drafts/publish-batch', {
			method: 'POST',
			body: JSON.stringify({ ids: selectedIds.value.slice() })
		})
		const parts = ['已发布 ' + result.ok + ' 条']
		if (result.fail) {
			parts.push('失败 ' + result.fail + ' 条')
		}
		parts.push('系统默认课程会自动补进')
		message.value = parts.join('，')
		dropSelected((result.items || []).map((item) => item.draft_id || item.draftId).concat(selectedIds.value))
		if (result.fail) {
			error.value = (result.errors || []).map((item) => '#' + item.id + ' ' + item.detail).join('；')
		}
		await loadDrafts()
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

async function discard(id) {
	error.value = ''
	busy.value = true
	try {
		await request('/drafts/' + id, {
			method: 'PATCH',
			body: JSON.stringify({ status: 'discarded' })
		})
		dropSelected([id])
		await loadDrafts()
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

watch(() => route.query.resourceId, applyResourceQuery)

onMounted(async () => {
	applyResourceQuery()
	loading.value = true
	try {
		await loadDrafts()
	} catch (err) {
		error.value = err.message
	} finally {
		loading.value = false
	}
})
</script>
