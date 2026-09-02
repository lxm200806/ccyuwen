<template>
	<div>
		<section class="card">
			<h2>上传原始资源</h2>
			<p class="muted">官方文件进 official 目录，仅管理员。抽取前只存档。</p>
			<div class="row">
				<label>
					范围
					<select v-model="scope">
						<option value="official">官方</option>
						<option value="user">当前用户</option>
					</select>
				</label>
				<label>
					文件
					<input type="file" @change="onFile">
				</label>
			</div>
			<button type="button" @click="upload">上传</button>
			<p v-if="message" class="muted">{{ message }}</p>
			<p v-if="error" class="error">{{ error }}</p>
		</section>

		<section class="card">
			<h2>抽取到草稿库</h2>
			<label for="resource-id">关联资源 ID（可选）</label>
			<input id="resource-id" v-model="resourceId" placeholder="上传后的 id">
			<label for="import-text">CSV 或 JSON</label>
			<textarea id="import-text" v-model="importText" placeholder='kind,level,prompt,answer,tags,source'></textarea>
			<button type="button" @click="importDrafts">写入草稿</button>
		</section>

		<section class="card">
			<h2>草稿审核</h2>
			<div v-if="drafts.length === 0" class="muted">暂无待审草稿</div>
			<article v-for="item in drafts" :key="item.id" class="lib-item">
				<p><b>#{{ item.id }}</b> {{ item.kind }} / {{ item.level }}</p>
				<p>{{ item.prompt }}</p>
				<p class="muted">{{ item.answer }}</p>
				<button type="button" @click="publish(item.id)">发布</button>
				<button class="ghost" type="button" @click="discard(item.id)">弃用</button>
			</article>
		</section>
	</div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { request } from '../api.js'

const scope = ref('official')
const file = ref(null)
const resourceId = ref('')
const importText = ref('')
const drafts = ref([])
const message = ref('')
const error = ref('')

function onFile(event) {
	file.value = event.target.files && event.target.files[0] ? event.target.files[0] : null
}

async function upload() {
	error.value = ''
	if (!file.value) {
		error.value = '请选择文件'
		return
	}
	const body = new FormData()
	body.append('scope', scope.value)
	body.append('file', file.value)
	try {
		const saved = await request('/resources', { method: 'POST', body })
		message.value = '已保存 #' + saved.id + ' → ' + saved.path
		resourceId.value = String(saved.id)
	} catch (err) {
		error.value = err.message
	}
}

async function loadDrafts() {
	drafts.value = await request('/drafts?status=draft')
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

onMounted(loadDrafts)
</script>
