/**
 * 默写与词库界面
 * @module js/app
 * @author ccyuwen
 * @version 1.0.0
 * @created 2026-09-02
 */
(function () {
	const KIND_LABEL = { poem: '古诗', idiom: '成语', zi: '易错字' }
	const LEVEL_LABEL = {
		L1: 'L1 课内必背',
		L2: 'L2 课内拓展',
		L3: 'L3 小升初高频',
		L4: 'L4 竞赛超纲'
	}
	const QUALITY_LABEL = { 1: '再练', 3: '模糊', 5: '全对' }

	const page = {
		queue: [],
		index: 0,
		tab: 'drill'
	}

	/**
	 * @param {string} id
	 * @returns {HTMLElement|null}
	 */
	function $(id) {
		return document.getElementById(id)
	}

	function boot() {
		if (!$('app')) {
			return
		}
		CcyuwenStore.ensureSeed()
		bindEvents()
		showTab('drill')
	}

	function bindEvents() {
		document.querySelectorAll('[data-tab]').forEach(function (btn) {
			btn.addEventListener('click', function () {
				showTab(btn.getAttribute('data-tab'))
			})
		})
		$('btn-submit').addEventListener('click', submitAnswer)
		$('btn-reveal').addEventListener('click', revealAnswer)
		$('btn-next').addEventListener('click', nextCard)
		$('btn-speak').addEventListener('click', speakPrompt)
		$('answer-input').addEventListener('keydown', function (event) {
			if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
				submitAnswer()
			}
		})
		$('filter-kind').addEventListener('change', renderLibrary)
		$('filter-level').addEventListener('change', renderLibrary)
		$('btn-add').addEventListener('click', saveEditor)
		$('btn-import').addEventListener('click', runImport)
		$('btn-export').addEventListener('click', runExport)
		$('btn-print').addEventListener('click', function () {
			window.print()
		})
	}

	/**
	 * @param {string} name
	 */
	function showTab(name) {
		page.tab = name
		document.querySelectorAll('.tab-page').forEach(function (el) {
			el.hidden = el.getAttribute('data-page') !== name
		})
		document.querySelectorAll('[data-tab]').forEach(function (btn) {
			btn.classList.toggle('is-on', btn.getAttribute('data-tab') === name)
		})
		if (name === 'drill') {
			startDrill()
		} else if (name === 'library') {
			renderLibrary()
		} else if (name === 'progress') {
			renderProgress()
		}
	}

	function startDrill() {
		page.queue = CcyuwenStore.buildTodayQueue()
		page.index = 0
		$('result-box').hidden = true
		$('answer-input').value = ''
		renderDrill()
	}

	function currentCard() {
		return page.queue[page.index] || null
	}

	function renderDrill() {
		const card = currentCard()
		const stats = CcyuwenStore.stats()
		$('drill-meta').textContent = '今日 ' + page.queue.length + ' 张 · 到期 ' + stats.due + ' · 未学 ' + stats.fresh
		if (!card) {
			$('prompt-text').textContent = '今天的默写做完了。'
			$('prompt-tag').textContent = '休息一下'
			$('answer-input').hidden = true
			$('drill-actions').hidden = true
			$('result-box').hidden = true
			return
		}
		$('answer-input').hidden = false
		$('drill-actions').hidden = false
		$('prompt-text').textContent = card.prompt
		$('prompt-tag').textContent = LEVEL_LABEL[card.level] + ' · ' + KIND_LABEL[card.kind]
		$('card-progress').textContent = (page.index + 1) + ' / ' + page.queue.length
	}

	function submitAnswer() {
		const card = currentCard()
		if (!card) {
			return
		}
		const input = $('answer-input').value
		const result = CcyuwenGrade.gradeAnswer(input, card.answer)
		CcyuwenStore.reviewPoint(card.id, result.quality)
		showResult(card, result)
		if (result.quality < 3) {
			page.queue.push(card)
		}
	}

	function revealAnswer() {
		const card = currentCard()
		if (!card) {
			return
		}
		const result = CcyuwenGrade.gradeAnswer('', card.answer)
		result.quality = 1
		CcyuwenStore.reviewPoint(card.id, 1)
		showResult(card, result)
		page.queue.push(card)
	}

	/**
	 * @param {Object} card
	 * @param {Object} result
	 */
	function showResult(card, result) {
		$('answer-input').hidden = true
		$('drill-actions').hidden = true
		$('result-box').hidden = false
		$('result-title').textContent = QUALITY_LABEL[result.quality] || '再练'
		$('result-title').className = 'result-title q' + result.quality
		$('result-answer').textContent = card.answer
		$('result-diff').innerHTML = result.chars.map(function (item) {
			const cls = item.ok ? 'ok' : 'bad'
			return '<span class="' + cls + '">' + escapeHtml(item.char) + '</span>'
		}).join('')
	}

	function nextCard() {
		page.index += 1
		$('result-box').hidden = true
		$('answer-input').hidden = false
		$('drill-actions').hidden = false
		$('answer-input').value = ''
		$('answer-input').focus()
		renderDrill()
	}

	function speakPrompt() {
		const card = currentCard()
		if (!card || !window.speechSynthesis) {
			return
		}
		window.speechSynthesis.cancel()
		const utter = new SpeechSynthesisUtterance(card.prompt)
		utter.lang = 'zh-CN'
		utter.rate = 0.85
		window.speechSynthesis.speak(utter)
	}

	function renderLibrary() {
		const kind = $('filter-kind').value
		const level = $('filter-level').value
		const state = CcyuwenStore.load()
		const rows = state.points.filter(function (item) {
			if (kind && item.kind !== kind) {
				return false
			}
			if (level && item.level !== level) {
				return false
			}
			return true
		})
		$('lib-count').textContent = rows.length + ' 条'
		$('lib-list').innerHTML = rows.map(function (item) {
			return (
				'<article class="lib-card" data-id="' + escapeAttr(item.id) + '">' +
					'<p class="lib-prompt">' + escapeHtml(item.prompt) + '</p>' +
					'<p class="lib-answer">' + escapeHtml(item.answer) + '</p>' +
					'<p class="lib-meta">' + escapeHtml(LEVEL_LABEL[item.level] + ' · ' + KIND_LABEL[item.kind]) + '</p>' +
					'<div class="lib-ops">' +
						'<button type="button" data-edit="' + escapeAttr(item.id) + '">编辑</button>' +
						'<button type="button" data-del="' + escapeAttr(item.id) + '">删除</button>' +
					'</div>' +
				'</article>'
			)
		}).join('')
		$('lib-list').querySelectorAll('[data-edit]').forEach(function (btn) {
			btn.addEventListener('click', function () {
				fillEditor(btn.getAttribute('data-edit'))
			})
		})
		$('lib-list').querySelectorAll('[data-del]').forEach(function (btn) {
			btn.addEventListener('click', function () {
				if (window.confirm('删除这条知识点？')) {
					CcyuwenStore.removePoint(btn.getAttribute('data-del'))
					renderLibrary()
					clearEditor()
				}
			})
		})
	}

	/**
	 * @param {string} id
	 */
	function fillEditor(id) {
		const point = CcyuwenStore.load().points.find(function (item) {
			return item.id === id
		})
		if (!point) {
			return
		}
		$('edit-id').value = point.id
		$('edit-kind').value = point.kind
		$('edit-level').value = point.level
		$('edit-prompt').value = point.prompt
		$('edit-answer').value = point.answer
		$('edit-tags').value = point.tags
		$('edit-source').value = point.source
		$('edit-prompt').focus()
	}

	function clearEditor() {
		$('edit-id').value = ''
		$('edit-prompt').value = ''
		$('edit-answer').value = ''
		$('edit-tags').value = ''
		$('edit-source').value = ''
	}

	function saveEditor() {
		const saved = CcyuwenStore.upsertPoint({
			id: $('edit-id').value,
			kind: $('edit-kind').value,
			level: $('edit-level').value,
			prompt: $('edit-prompt').value,
			answer: $('edit-answer').value,
			tags: $('edit-tags').value,
			source: $('edit-source').value
		})
		if (!saved) {
			window.alert('请填写提示和答案')
			return
		}
		clearEditor()
		renderLibrary()
	}

	function renderProgress() {
		const info = CcyuwenStore.stats()
		$('stat-total').textContent = String(info.total)
		$('stat-due').textContent = String(info.due)
		$('stat-fresh').textContent = String(info.fresh)
		$('stat-mastered').textContent = String(info.mastered)
		$('stat-weak').textContent = String(info.weak)
		const state = CcyuwenStore.load()
		const groups = { L1: 0, L2: 0, L3: 0, L4: 0 }
		state.points.forEach(function (item) {
			groups[item.level] = (groups[item.level] || 0) + 1
		})
		$('level-bars').innerHTML = Object.keys(groups).map(function (level) {
			const count = groups[level]
			const width = info.total ? Math.round((count / info.total) * 100) : 0
			return (
				'<div class="bar-row">' +
					'<span>' + escapeHtml(LEVEL_LABEL[level]) + '</span>' +
					'<div class="bar"><i style="width:' + width + '%"></i></div>' +
					'<em>' + count + '</em>' +
				'</div>'
			)
		}).join('')
	}

	function runImport() {
		const parsed = CcyuwenStore.parseImport($('import-text').value)
		if (parsed.ok.length === 0) {
			window.alert('没有解析到有效知识点。格式：JSON 数组，或 CSV 表头 kind,level,prompt,answer,tags,source')
			return
		}
		const added = CcyuwenStore.importPoints(parsed.ok, parsed.reviews)
		window.alert('写入 ' + parsed.ok.length + ' 条（新增 ' + added + '，跳过 ' + parsed.skip + '）')
		$('import-text').value = ''
		renderLibrary()
	}

	function runExport() {
		const blob = new Blob([CcyuwenStore.exportJson()], { type: 'application/json' })
		const url = URL.createObjectURL(blob)
		const link = document.createElement('a')
		link.href = url
		link.download = 'ccyuwen-backup.json'
		link.click()
		URL.revokeObjectURL(url)
	}

	/**
	 * @param {string} text
	 * @returns {string}
	 */
	function escapeHtml(text) {
		return String(text)
			.replace(/&/g, '&amp;')
			.replace(/</g, '&lt;')
			.replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;')
	}

	/**
	 * @param {string} text
	 * @returns {string}
	 */
	function escapeAttr(text) {
		return escapeHtml(text)
	}

	document.addEventListener('DOMContentLoaded', boot)
})()
