<template>
	<section class="card">
		<h2>全部知识点</h2>
		<p class="muted">已发布库，管理员可改题目和答案。课程快照里的旧文案不会自动变。</p>
		<div class="row">
			<label>
				类型
				<select v-model="kind">
					<option value="">全部</option>
					<option value="poem">古诗</option>
					<option value="idiom">成语</option>
					<option value="zi">易错字</option>
				</select>
			</label>
			<label>
				级别
				<select v-model="level">
					<option value="">全部</option>
					<option value="L1">L1</option>
					<option value="L2">L2</option>
					<option value="L3">L3</option>
					<option value="L4">L4</option>
				</select>
			</label>
		</div>
		<p class="muted">共 {{ points.length }} 条</p>
		<p v-if="error" class="error">{{ error }}</p>
		<p v-if="message" class="ok">{{ message }}</p>

		<div v-if="editing" class="card">
			<h3>编辑 #{{ editing.id }}</h3>
			<div class="row">
				<label>
					类型
					<select v-model="editing.kind">
						<option value="poem">古诗</option>
						<option value="idiom">成语</option>
						<option value="zi">易错字</option>
					</select>
				</label>
				<label>
					级别
					<select v-model="editing.level">
						<option value="L1">L1</option>
						<option value="L2">L2</option>
						<option value="L3">L3</option>
						<option value="L4">L4</option>
					</select>
				</label>
			</div>
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

		<article v-for="item in points" :key="item.id">
			<p><b>#{{ item.id }}</b> {{ item.level }} · {{ kindLabel[item.kind] }}</p>
			<p>{{ item.prompt }}</p>
			<p class="muted">{{ item.answer }}</p>
			<button class="ghost" type="button" @click="startEdit(item)">编辑</button>
		</article>
	</section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { request } from '../api.js'

const kindLabel = { poem: '古诗', idiom: '成语', zi: '易错字' }
const kind = ref('')
const level = ref('')
const points = ref([])
const editing = ref(null)
const error = ref('')
const message = ref('')

async function loadPoints() {
	error.value = ''
	const query = []
	if (kind.value) {
		query.push('kind=' + encodeURIComponent(kind.value))
	}
	if (level.value) {
		query.push('level=' + encodeURIComponent(level.value))
	}
	const suffix = query.length ? '?' + query.join('&') : ''
	points.value = await request('/library' + suffix)
}

function startEdit(item) {
	editing.value = {
		id: item.id,
		kind: item.kind,
		level: item.level,
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

watch([kind, level], loadPoints)
onMounted(loadPoints)
</script>
