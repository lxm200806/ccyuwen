<template>
	<section class="card">
		<p class="muted">{{ meta }}</p>
		<template v-if="card">
			<p class="muted">{{ card.level }} · {{ card.kind }} · {{ index + 1 }} / {{ queue.length }}</p>
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
	meta.value = '今日 ' + data.items.length + ' 张 · 到期 ' + data.due + ' · 未学 ' + data.fresh
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
