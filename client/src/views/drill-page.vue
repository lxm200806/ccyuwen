<template>
	<section class="card">
		<div class="mode-switch" role="tablist" aria-label="学习模式">
			<button
				v-for="item in modeOptions"
				:key="item.id"
				type="button"
				role="tab"
				:aria-selected="mode === item.id"
				:class="{ active: mode === item.id }"
				:disabled="loading || modeLocked"
				@click="selectMode(item.id)"
			>
				<strong>{{ item.label }}</strong>
				<span>{{ item.hint }}</span>
			</button>
		</div>
		<p v-if="loading" class="muted">正在准备今日默写…</p>
		<template v-else>
			<p class="muted">{{ meta }}</p>
			<p class="hint">
				「能」是今天的学习量：字 1、词语 2、成语 4，古诗 / 文言文按篇幅。每天先按<strong>复习能量</strong>收到期的学习卡，再按<strong>新学能量</strong>收还没学过的卡。一张<strong>学习卡</strong>是同一模块的几条知识点，捆在一起默写。
			</p>
			<p class="hint">{{ modeHint }}</p>
			<template v-if="card">
				<p class="muted">
					{{ card.grade || '未分年级' }} · {{ levelLabel(card.level) }} · {{ kindLabel(card.kind) }}
					· {{ card.role === 'review' ? '复习' : '新学' }}
					· 第 {{ card.taskIndex || index + 1 }} / {{ card.taskCount || queue.length }} 张学习卡
				</p>
				<p v-if="card.groupSize > 1" class="muted">本卡 {{ card.groupIndex }} / {{ card.groupSize }} · {{ card.groupEnergy || 0 }} 能</p>
				<p v-if="card.parts > 1" class="muted">大卡拆天：{{ card.part }} / {{ card.parts }}</p>
				<p class="muted">知识点 {{ index + 1 }} / {{ queue.length }} · 本条 {{ card.energy || 0 }} 能</p>
				<p v-if="card.source && mode !== 'test'" class="muted">{{ card.source }}</p>
				<h2>{{ card.prompt }}</h2>
				<template v-if="mode === 'recite' && !result">
					<button class="danger" type="button" :disabled="busy" @click="speak">听写朗读</button>
					<div class="recite-lines" aria-live="polite">
						<p
							v-for="(line, lineIndex) in reciteLines"
							:key="lineIndex"
							class="recite-line"
							:class="{ covered: lineIndex >= revealedCount }"
						>{{ lineIndex >= revealedCount ? '（已遮住）' : line }}</p>
					</div>
					<button
						class="ghost"
						type="button"
						:disabled="busy || revealedCount >= reciteLines.length"
						@click="revealNext"
					>显示下一行</button>
					<button
						v-if="revealedCount < reciteLines.length"
						class="ghost"
						type="button"
						:disabled="busy"
						@click="revealAll"
					>对照全文</button>
					<button type="button" :disabled="busy" @click="nextCard">下一题</button>
					<details class="recite-optional">
						<summary>也可以默写核对（可选，不记间隔）</summary>
						<label for="answer">默写答案</label>
						<textarea id="answer" v-model="answer" :disabled="busy"></textarea>
						<button class="ghost" type="button" :disabled="busy" @click="submit(false)">核对</button>
					</details>
				</template>
				<template v-else-if="!result">
					<label for="answer">默写答案</label>
					<textarea id="answer" v-model="answer" :disabled="busy"></textarea>
					<button class="danger" type="button" :disabled="busy" @click="submit(false)">提交</button>
					<button
						v-if="mode === 'learn'"
						class="ghost"
						type="button"
						:disabled="busy"
						@click="submit(true)"
					>不会，看答案</button>
					<button class="ghost" type="button" :disabled="busy" @click="speak">听写朗读</button>
				</template>
				<div v-else>
					<p :class="result.correct ? 'ok' : 'error'">
						{{ resultLabel }}
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
			<div v-else-if="itemCount === 0" class="hint">
				<p>这门课还没有知识点，所以没有今日默写。</p>
				<p>
					请回
					<router-link to="/courses">我的课程</router-link>
					点「同步新词」，或去
					<router-link to="/library">组课</router-link>
					按年级生成一份。
				</p>
			</div>
			<div v-else class="hint">
				<p>{{ emptyHint }}</p>
				<p>
					明天再来，或打开
					<router-link :to="'/courses/' + route.params.id + '/plan'">学习计划</router-link>
					看后面几天。也可以换一个模式再试试。
				</p>
			</div>
		</template>
		<p v-if="error" class="error">{{ error }}</p>
	</section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../api.js'
import { kindLabel, levelLabel } from '../catalog.js'

const MODE_OPTIONS = [
	{ id: 'learn', label: '学习', hint: '先练会' },
	{ id: 'test', label: '测试', hint: '考考你' },
	{ id: 'recite', label: '背诵', hint: '读出来' }
]

const route = useRoute()
const router = useRouter()
const queue = ref([])
const index = ref(0)
const answer = ref('')
const result = ref(null)
const meta = ref('')
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const itemCount = ref(0)
const mode = ref('learn')
const energyCharged = ref(true)
const revealedCount = ref(0)
const modeOptions = MODE_OPTIONS

const card = computed(() => queue.value[index.value] || null)
const reciteLines = computed(() => {
	if (!card.value) {
		return []
	}
	if (Array.isArray(card.value.lines) && card.value.lines.length) {
		return card.value.lines
	}
	const text = String(card.value.answer || '').trim()
	return text ? [text] : ['（暂无原文）']
})
const modeLocked = computed(() => {
	return busy.value || !!result.value || !!String(answer.value || '').trim() || revealedCount.value > 0
})
const modeHint = computed(() => {
	if (mode.value === 'test') {
		return '测试是正式默写：少提示、提交前不能看答案，对错按严格间隔记。优先做到期复习卡。'
	}
	if (mode.value === 'recite') {
		return '背诵练听和读：可以逐行对照。不改间隔记忆，也不消耗今日新学 / 复习能量。'
	}
	return '学习先练会：可以看出处，不会时可以看答案。看过答案记为「模糊」，比写错轻，不记 lapse。'
})
const resultLabel = computed(() => {
	if (!result.value) {
		return ''
	}
	if (result.value.updateSm2 === false) {
		return result.value.correct ? '对照一致（背诵不记间隔）' : '再读一读（背诵不记间隔）'
	}
	if (result.value.revealed) {
		return '看过答案 · 记为模糊'
	}
	return result.value.correct ? '全对' : (result.value.quality === 3 ? '模糊' : '再练')
})
const emptyHint = computed(() => {
	if (mode.value === 'test') {
		return '今天没有到期复习卡可测。可以切到「学习」练新卡，或明天再来。'
	}
	if (mode.value === 'recite') {
		return '今天没有可朗读的学习卡。'
	}
	return '今天的默写做完了。新学和复习能量都已用完（或没有到期卡片）。'
})

async function loadToday(nextMode) {
	loading.value = true
	error.value = ''
	try {
		const requested = nextMode || route.query.mode || ''
		const suffix = requested ? ('?mode=' + encodeURIComponent(requested)) : ''
		const data = await request('/courses/' + route.params.id + '/today' + suffix)
		queue.value = data.items
		index.value = 0
		result.value = null
		answer.value = ''
		revealedCount.value = 0
		itemCount.value = Number(data.itemCount) || 0
		mode.value = data.mode || 'learn'
		energyCharged.value = data.energyCharged !== false
		if (energyCharged.value) {
			meta.value = '今日新学 ' + (data.newEnergy || 0) + '/' + (data.newBudget || 30) + ' 能 · 复习 ' + (data.reviewEnergy || 0) + '/' + (data.reviewBudget || 30) + ' 能 · ' + (data.tasks || 0) + ' 张学习卡 / ' + (data.cards || data.items.length) + ' 个知识点'
		} else {
			meta.value = '背诵不计能量 · ' + (data.tasks || 0) + ' 张学习卡 / ' + (data.cards || data.items.length) + ' 个知识点可朗读（新学预算 ' + (data.newBudget || 30) + ' 能 / 复习预算 ' + (data.reviewBudget || 30) + ' 能）'
		}
		if (route.query.mode !== mode.value) {
			router.replace({ query: { mode: mode.value } })
		}
	} catch (err) {
		error.value = err.message
		queue.value = []
		itemCount.value = 0
	} finally {
		loading.value = false
	}
}

function selectMode(id) {
	if (id === mode.value || modeLocked.value) {
		return
	}
	loadToday(id)
}

async function submit(reveal) {
	error.value = ''
	busy.value = true
	try {
		const data = await request('/courses/' + route.params.id + '/review', {
			method: 'POST',
			body: JSON.stringify({
				pointId: card.value.id,
				answer: answer.value,
				reveal: reveal,
				mode: mode.value
			})
		})
		result.value = data
		if (data.updateSm2 !== false && data.quality < 3) {
			queue.value.push(card.value)
		}
	} catch (err) {
		error.value = err.message
	} finally {
		busy.value = false
	}
}

function nextCard() {
	index.value += 1
	result.value = null
	answer.value = ''
	revealedCount.value = 0
}

function revealNext() {
	if (revealedCount.value < reciteLines.value.length) {
		revealedCount.value += 1
	}
}

function revealAll() {
	revealedCount.value = reciteLines.value.length
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
