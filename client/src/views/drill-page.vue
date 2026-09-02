<template>
	<section class="card">
		<p class="muted">{{ meta }}</p>
		<template v-if="card">
			<p class="muted">{{ card.grade || '未分年级' }} · {{ levelLabel(card.level) }} · {{ kindLabel(card.kind) }} · 第 {{ card.taskIndex || index + 1 }} / {{ card.taskCount || queue.length }} 张学习卡</p>
			<p v-if="card.groupSize > 1" class="muted">本卡 {{ card.groupIndex }} / {{ card.groupSize }} · {{ card.groupEnergy || 0 }} 能</p>
			<p v-if="card.parts > 1" class="muted">大卡拆天：{{ card.part }} / {{ card.parts }}</p>
			<p class="muted">知识点 {{ index + 1 }} / {{ queue.length }} · 本条 {{ card.energy || 0 }} 能</p>
			<p v-if="card.source" class="muted">{{ card.source }}</p>
			<h2>{{ card.prompt }}</h2>
			<template v-if="!result">
				<label for="answer">默写答案</label>
				<textarea id="answer" v-model="answer"></textarea>
				<button class="danger" type="button" @click="submit(false)">提交</button>
				<button class="ghost" type="button" @click="submit(true)">不会，看答案</button>
				<button class="ghost" type="button" @click="speak">听写朗读</button>
			</template>
			<div v-else>
				<p :class="result.correct ? 'ok' : 'error'">
					{{ result.correct ? '全对' : (result.quality === 3 ? '模糊' : '再练') }}
				</p>
				<p>标准答案：{{ result.answer }}</p>
				<p>
					对照：
					<span
						v-for="(ch, i) in result.chars"
						:key="i"
						:class="ch.ok ? 'ok' : 'bad'"
					>{{ ch.char }}</span>
				</p>
				<button type="button" @click="nextCard">下一题</button>
			</div>
		</template>
		<p v-else>今天的默写做完了。</p>
		<p v-if="error" class="error">{{ error }}</p>
	</section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../api.js'
import { kindLabel, levelLabel } from '../catalog.js'

const route = useRoute()
const queue = ref([])
const index = ref(0)
const answer = ref('')
const result = ref(null)
const meta = ref('')
const error = ref('')

const card = computed(() => queue.value[index.value] || null)

async function loadToday() {
	const data = await request('/courses/' + route.params.id + '/today')
	queue.value = data.items
	index.value = 0
	result.value = null
	answer.value = ''
	meta.value = '今日新学 ' + (data.newEnergy || 0) + '/' + (data.newBudget || 30) + ' 能 · 复习 ' + (data.reviewEnergy || 0) + '/' + (data.reviewBudget || 30) + ' 能 · ' + (data.tasks || 0) + ' 张学习卡 / ' + (data.cards || data.items.length) + ' 个知识点'
}

async function submit(reveal) {
	error.value = ''
	try {
		const data = await request('/courses/' + route.params.id + '/review', {
			method: 'POST',
			body: JSON.stringify({
				pointId: card.value.id,
				answer: answer.value,
				reveal: reveal
			})
		})
		result.value = data
		if (data.quality < 3) {
			queue.value.push(card.value)
		}
	} catch (err) {
		error.value = err.message
	}
}

function nextCard() {
	index.value += 1
	result.value = null
	answer.value = ''
}

function speak() {
	if (!card.value || !window.speechSynthesis) {
		return
	}
	window.speechSynthesis.cancel()
	const utter = new SpeechSynthesisUtterance(card.value.prompt)
	utter.lang = 'zh-CN'
	utter.rate = 0.85
	window.speechSynthesis.speak(utter)
}

onMounted(loadToday)
</script>
