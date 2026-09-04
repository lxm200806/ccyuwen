<template>
	<div>
		<section class="card">
			<h2>上传原始资源</h2>
			<p class="muted">仅管理员可上传。官方文件进 official 目录，抽取前只存档。</p>
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
			<p v-if="message" class="ok">{{ message }}</p>
			<p v-if="error" class="error">{{ error }}</p>
		</section>

		<section class="card">
			<h2>已备份的原始材料</h2>
			<p class="muted">改 <code>raw/部编…册.json</code>、<code>raw/idioms/小学成语.json</code> 或对应 md 后刷新本页。系统用内容指纹对比上次同步：灰色「未同步」、红色「有更新」、绿色「已同步」。文件版本大于已同步版本，也说明内容变了。十二册和小学成语同步后直接进知识库，不用审核。小学成语课内条目按年级，分日积月累 / 课文。</p>
			<div class="course-actions">
				<button type="button" :disabled="syncing" @click="syncIncremental">增量同步</button>
				<button class="ghost" type="button" :disabled="syncing" @click="syncAllPacks">一键重新同步</button>
			</div>
			<div v-if="officialPacks.length === 0 && otherResources.length === 0" class="muted">还没有资源</div>
			<article v-for="item in officialPacks" :key="item.id">
				<p>
					<b>#{{ item.id }}</b> {{ item.title || item.filename }}
					<span class="sync-tag" :class="item.syncState">{{ syncLabel(item) }}</span>
				</p>
				<p class="muted">{{ item.filename }} · 文件 v{{ item.version }} · 已同步 v{{ item.syncedVersion || 0 }} · {{ item.pointCount }} 条</p>
				<p v-if="item.syncState === 'outdated'" class="error">内容已变化，尚未同步到知识库。</p>
				<p v-else-if="item.syncState === 'pending'" class="error">尚未写入知识库。</p>
				<div class="course-actions">
					<button type="button" :disabled="syncing" @click="syncResource(item.id)">同步到知识库</button>
					<button class="ghost" type="button" @click="previewResource(item.id)">查看原文</button>
					<button class="ghost" type="button" @click="useForExtract(item.id)">用作抽取</button>
				</div>
			</article>
			<template v-if="originalFiles.length">
				<h3>原文备份</h3>
				<article v-for="item in originalFiles" :key="item.id">
					<p><b>#{{ item.id }}</b> {{ item.filename }}</p>
					<p class="muted">{{ item.path }}{{ item.slug ? ' · ' + item.slug : '' }}</p>
					<div class="course-actions">
						<button class="ghost" type="button" @click="previewResource(item.id)">查看原文</button>
					</div>
				</article>
			</template>
			<template v-if="otherResources.length">
				<h3>其他上传</h3>
				<article v-for="item in otherResources" :key="item.id">
					<p><b>#{{ item.id }}</b> {{ item.filename }}</p>
					<p class="muted">{{ item.owner_type }} · {{ item.path }} · {{ item.status }}{{ item.slug ? ' · ' + item.slug : '' }}</p>
					<div class="course-actions">
						<button type="button" :disabled="syncing" @click="syncResource(item.id)">同步到知识库</button>
						<button class="ghost" type="button" @click="previewResource(item.id)">查看原文</button>
						<button class="ghost" type="button" @click="useForExtract(item.id)">用作抽取</button>
					</div>
				</article>
			</template>
			<pre v-if="preview" class="original-preview">{{ preview }}</pre>
		</section>
	</div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { request } from '../api.js'

const router = useRouter()
const scope = ref('official')
const file = ref(null)
const resources = ref([])
const officialPacks = computed(() => resources.value.filter((item) => item.isPack))
const originalFiles = computed(() => resources.value.filter((item) => item.isOriginal))
const otherResources = computed(() => resources.value.filter((item) => !item.isPack && !item.isOriginal))
const preview = ref('')
const message = ref('')
const error = ref('')
const syncing = ref(false)

function syncLabel(item) {
	if (item.syncState === 'synced') {
		return '已同步'
	}
	if (item.syncState === 'outdated') {
		return '有更新'
	}
	if (item.syncState === 'pending') {
		return '未同步'
	}
	return item.status || ''
}

function onFile(event) {
	file.value = event.target.files && event.target.files[0] ? event.target.files[0] : null
}

function useForExtract(id) {
	router.push({ name: 'Admin', query: { resourceId: String(id) } })
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
		await loadResources()
	} catch (err) {
		error.value = err.message
	}
}

async function loadResources() {
	resources.value = await request('/resources')
}

onMounted(async () => {
	try {
		await loadResources()
	} catch (err) {
		error.value = err.message
	}
})

async function previewResource(id) {
	error.value = ''
	try {
		const data = await request('/resources/' + id)
		preview.value = data.original || '（空）'
		message.value = data.filename + ' 已关联 ' + data.linkedPoints + ' 个知识点'
	} catch (err) {
		error.value = err.message
	}
}

async function syncResource(id) {
	error.value = ''
	syncing.value = true
	try {
		const result = await request('/resources/' + id + '/sync', { method: 'POST' })
		message.value = (result.title || result.filename) + '：新增 ' + result.inserted + '，更新 ' + result.updated + '，未改 ' + (result.unchanged || 0)
		await loadResources()
	} catch (err) {
		error.value = err.message
	} finally {
		syncing.value = false
	}
}

async function syncIncremental() {
	error.value = ''
	syncing.value = true
	try {
		const result = await request('/resources/sync-incremental', { method: 'POST' })
		message.value = '增量同步：写入 ' + result.synced + ' 册，跳过已同步 ' + result.skipped + ' 册，新增 ' + result.inserted + '，更新 ' + result.updated
		await loadResources()
	} catch (err) {
		error.value = err.message
	} finally {
		syncing.value = false
	}
}

async function syncAllPacks() {
	error.value = ''
	syncing.value = true
	try {
		const result = await request('/resources/sync-all', { method: 'POST' })
		message.value = '重新同步官方材料：新增 ' + result.inserted + '，更新 ' + result.updated
		await loadResources()
	} catch (err) {
		error.value = err.message
	} finally {
		syncing.value = false
	}
}
</script>
