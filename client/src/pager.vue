<template>
	<nav v-if="pageCount > 1" class="pager">
		<button class="ghost" type="button" :disabled="page <= 1" @click="go(page - 1)">上一页</button>
		<span class="muted">第 {{ page }} / {{ pageCount }} 页</span>
		<button class="ghost" type="button" :disabled="page >= pageCount" @click="go(page + 1)">下一页</button>
	</nav>
</template>

<script setup>
const props = defineProps({
	page: { type: Number, default: 1 },
	pageCount: { type: Number, default: 1 }
})
const emit = defineEmits(['update:page'])

function go(next) {
	const safe = Math.min(Math.max(1, next), Math.max(1, props.pageCount))
	if (safe !== props.page) {
		emit('update:page', safe)
	}
}
</script>
