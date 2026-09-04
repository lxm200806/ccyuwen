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
			<div v-else-if="drafts.length === 0" class="hint">
				<p>暂无待审草稿。</p>
				<p>
					系统预置的十二册教材在「原始资料」里同步后，会<strong>直接写入已发布库</strong>，不会出现在这个草稿队列。要更新课本内容，请打开
					<router-link to="/materials">原始资料</router-link>
					做增量同步或单册同步。只有在本页粘贴 CSV / JSON「写入草稿」的条目，才需要在这里审核发布。
				</p>
			</div>
			<p v-else class="muted">待审 {{ total }} 条</p>
			<article v-for="item in drafts" :key="item.id" class="lib-item">
				<p><b>#{{ item.id }}</b> {{ item.grade || '未分年级' }} · {{ item.kind }} / {{ item.level }}</p>
				<p>{{ item.prompt }}</p>
				<p class="muted">{{ item.answer }}</p>
				<button type="button" :disabled="busy" @click="publish(item.id)">发布</button>
				<button class="ghost" type="button" :disabled="busy" @click="discard(item.id)">弃用</button>
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
const loading = ref(true)
const busy = ref(false)

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
