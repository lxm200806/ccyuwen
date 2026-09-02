<template>
	<div>
		<section class="card">
			<h2>抽取到草稿库</h2>
			<p class="muted">可先在「原始资料」里点「用作抽取」，把资源 ID 带到这里。</p>
			<label for="resource-id">关联资源 ID（可选）</label>
			<input id="resource-id" v-model="resourceId" placeholder="上传后的 id">
			<label for="import-text">CSV 或 JSON</label>
			<textarea id="import-text" v-model="importText" placeholder='kind,level,grade,prompt,answer,tags,source'></textarea>
			<button type="button" @click="importDrafts">写入草稿</button>
			<p v-if="message" class="muted">{{ message }}</p>
			<p v-if="error" class="error">{{ error }}</p>
		</section>

		<section class="card">
			<h2>草稿审核</h2>
			<div v-if="drafts.length === 0" class="muted">暂无待审草稿</div>
			<p v-else class="muted">待审 {{ total }} 条</p>
			<article v-for="item in drafts" :key="item.id" class="lib-item">
				<p><b>#{{ item.id }}</b> {{ item.grade || '未分年级' }} · {{ item.kind }} / {{ item.level }}</p>
				<p>{{ item.prompt }}</p>
				<p class="muted">{{ item.answer }}</p>
				<button type="button" @click="publish(item.id)">发布</button>
				<button class="ghost" type="button" @click="discard(item.id)">弃用</button>
			</article>
		</section>
	</div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api.js'

const route = useRoute()
const resourceId = ref('')
const importText = ref('')
const drafts = ref([])
const total = ref(0)
const message = ref('')
const error = ref('')

function applyResourceQuery() {
	if (route.query.resourceId) {
		resourceId.value = String(route.query.resourceId)
	}
}

async function loadDrafts() {
	const data = await request('/drafts?status=draft')
	drafts.value = data.items || []
	total.value = data.total || 0
}

async function importDrafts() {
	error.value = ''
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
		await loadDrafts()
	} catch (err) {
		error.value = err.message
	}
}

async function publish(id) {
	error.value = ''
	try {
		await request('/drafts/' + id + '/publish', { method: 'POST' })
		await loadDrafts()
	} catch (err) {
		error.value = err.message
	}
}

async function discard(id) {
	await request('/drafts/' + id, {
		method: 'PATCH',
		body: JSON.stringify({ status: 'discarded' })
	})
	await loadDrafts()
}

watch(() => route.query.resourceId, applyResourceQuery)

onMounted(() => {
	applyResourceQuery()
	loadDrafts()
})
</script>
