/**
 * 本地知识库（localStorage）
 * @module js/store
 * @author ccyuwen
 * @version 1.0.0
 * @created 2026-09-02
 */
(function (global) {
	const STORAGE_KEY = 'ccyuwen.v1'
	const NEW_LIMIT = 8
	const TOTAL_LIMIT = 25
	const KINDS = ['poem', 'idiom', 'zi']
	const LEVELS = ['L1', 'L2', 'L3', 'L4']

	/**
	 * @returns {{points: Array, reviews: Object}}
	 */
	function emptyState() {
		return { points: [], reviews: {} }
	}

	/**
	 * @returns {{points: Array, reviews: Object}}
	 */
	function load() {
		try {
			const raw = global.localStorage.getItem(STORAGE_KEY)
			if (!raw) {
				return emptyState()
			}
			const data = JSON.parse(raw)
			if (!data || !Array.isArray(data.points)) {
				return emptyState()
			}
			if (!data.reviews || typeof data.reviews !== 'object') {
				data.reviews = {}
			}
			return data
		} catch (error) {
			return emptyState()
		}
	}

	/**
	 * @param {{points: Array, reviews: Object}} state
	 * @returns {boolean}
	 */
	function save(state) {
		if (!state || !Array.isArray(state.points)) {
			return false
		}
		global.localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
		return true
	}

	/**
	 * 首次打开时写入内置词表
	 * @returns {{points: Array, reviews: Object}}
	 */
	function ensureSeed() {
		const state = load()
		if (state.points.length > 0) {
			return state
		}
		const seed = global.CcyuwenSeed && global.CcyuwenSeed.points
		if (!seed) {
			return state
		}
		state.points = seed.map(function (item) {
			return Object.assign({}, item)
		})
		save(state)
		return state
	}

	/**
	 * @returns {string}
	 */
	function uid() {
		return 'p' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)
	}

	/**
	 * @param {Object} input
	 * @returns {Object|null}
	 */
	function normalizePoint(input) {
		if (!input || typeof input !== 'object') {
			return null
		}
		const prompt = String(input.prompt || '').trim()
		const answer = String(input.answer || '').trim()
		if (!prompt || !answer) {
			return null
		}
		const kind = KINDS.indexOf(input.kind) >= 0 ? input.kind : 'poem'
		const level = LEVELS.indexOf(input.level) >= 0 ? input.level : 'L1'
		return {
			id: String(input.id || uid()),
			kind: kind,
			level: level,
			prompt: prompt,
			answer: answer,
			tags: String(input.tags || '').trim(),
			source: String(input.source || '').trim()
		}
	}

	/**
	 * @param {Object} input
	 * @returns {Object|null}
	 */
	function upsertPoint(input) {
		const point = normalizePoint(input)
		if (!point) {
			return null
		}
		const state = load()
		const index = state.points.findIndex(function (item) {
			return item.id === point.id
		})
		if (index >= 0) {
			state.points[index] = point
		} else {
			state.points.push(point)
		}
		save(state)
		return point
	}

	/**
	 * @param {string} id
	 * @returns {boolean}
	 */
	function removePoint(id) {
		const state = load()
		const next = state.points.filter(function (item) {
			return item.id !== id
		})
		if (next.length === state.points.length) {
			return false
		}
		state.points = next
		delete state.reviews[id]
		save(state)
		return true
	}

	/**
	 * @param {string} today
	 * @returns {Array}
	 */
	function buildTodayQueue(today) {
		const sm2 = global.CcyuwenSm2
		const day = today || sm2.todayText()
		const state = load()
		const due = []
		const fresh = []
		state.points.forEach(function (point) {
			const review = state.reviews[point.id]
			if (!review || !review.last) {
				fresh.push(point)
				return
			}
			if (review.due <= day) {
				due.push(point)
			}
		})
		due.sort(function (a, b) {
			return String(state.reviews[a.id].due).localeCompare(String(state.reviews[b.id].due))
		})
		const picked = due.slice()
		let i = 0
		for (i = 0; i < fresh.length && picked.length < TOTAL_LIMIT && i < NEW_LIMIT; i += 1) {
			picked.push(fresh[i])
		}
		return picked.slice(0, TOTAL_LIMIT)
	}

	/**
	 * @param {string} id
	 * @param {number} quality
	 * @param {string} today
	 * @returns {Object|null}
	 */
	function reviewPoint(id, quality, today) {
		const sm2 = global.CcyuwenSm2
		const state = load()
		const exists = state.points.some(function (item) {
			return item.id === id
		})
		if (!exists) {
			return null
		}
		const next = sm2.schedule(state.reviews[id], quality, today || sm2.todayText())
		state.reviews[id] = next
		save(state)
		return next
	}

	/**
	 * @returns {{total: number, due: number, fresh: number, mastered: number, weak: number}}
	 */
	function stats() {
		const sm2 = global.CcyuwenSm2
		const day = sm2.todayText()
		const state = load()
		let due = 0
		let fresh = 0
		let mastered = 0
		let weak = 0
		state.points.forEach(function (point) {
			const review = state.reviews[point.id]
			if (!review || !review.last) {
				fresh += 1
				return
			}
			if (sm2.isMastered(review)) {
				mastered += 1
			}
			if (Number(review.lapses) > 0 && Number(review.interval) <= 3) {
				weak += 1
			}
			if (review.due <= day) {
				due += 1
			}
		})
		return {
			total: state.points.length,
			due: due,
			fresh: fresh,
			mastered: mastered,
			weak: weak
		}
	}

	/**
	 * 解析 CSV 或 JSON 数组
	 * @param {string} text
	 * @returns {{ok: Array, skip: number}}
	 */
	function parseImport(text) {
		const raw = String(text || '').replace(/^\uFEFF/, '').trim()
		if (!raw) {
			return { ok: [], skip: 0 }
		}
		if (raw.charAt(0) === '[' || raw.charAt(0) === '{') {
			try {
				const data = JSON.parse(raw)
				if (Array.isArray(data)) {
					return collectRows(data)
				}
				if (data && Array.isArray(data.points)) {
					const parsed = collectRows(data.points)
					parsed.reviews = data.reviews
					return parsed
				}
				return { ok: [], skip: 1 }
			} catch (error) {
				return { ok: [], skip: 1 }
			}
		}
		return collectRows(parseCsv(raw))
	}

	/**
	 * @param {Array} rows
	 * @returns {{ok: Array, skip: number}}
	 */
	function collectRows(rows) {
		if (!Array.isArray(rows)) {
			return { ok: [], skip: 1 }
		}
		const ok = []
		let skip = 0
		rows.forEach(function (row) {
			const point = normalizePoint(row)
			if (point) {
				ok.push(point)
			} else {
				skip += 1
			}
		})
		return { ok: ok, skip: skip }
	}

	/**
	 * @param {string} text
	 * @returns {Array}
	 */
	function parseCsv(text) {
		const lines = String(text).split(/\r?\n/).filter(function (line) {
			return line.trim()
		})
		if (lines.length === 0) {
			return []
		}
		const headers = splitCsvLine(lines[0]).map(function (item) {
			return item.trim()
		})
		return lines.slice(1).map(function (line) {
			const cells = splitCsvLine(line)
			const row = {}
			headers.forEach(function (key, index) {
				row[key] = cells[index] || ''
			})
			return row
		})
	}

	/**
	 * @param {string} line
	 * @returns {Array<string>}
	 */
	function splitCsvLine(line) {
		const cells = []
		let current = ''
		let inQuote = false
		let i = 0
		for (i = 0; i < line.length; i += 1) {
			const ch = line.charAt(i)
			if (ch === '"') {
				inQuote = !inQuote
			} else if (ch === ',' && !inQuote) {
				cells.push(current)
				current = ''
			} else {
				current += ch
			}
		}
		cells.push(current)
		return cells
	}

	/**
	 * @param {Array} points
	 * @returns {number}
	 */
	function importPoints(points, reviews) {
		const state = load()
		let added = 0
		points.forEach(function (item) {
			const point = normalizePoint(item)
			if (!point) {
				return
			}
			const index = state.points.findIndex(function (old) {
				return old.id === point.id || (old.prompt === point.prompt && old.answer === point.answer)
			})
			if (index >= 0) {
				point.id = state.points[index].id
				state.points[index] = point
			} else {
				state.points.push(point)
				added += 1
			}
		})
		if (reviews && typeof reviews === 'object') {
			state.reviews = Object.assign({}, state.reviews, reviews)
		}
		save(state)
		return added
	}

	/**
	 * @returns {string}
	 */
	function exportJson() {
		return JSON.stringify(load(), null, 2)
	}

	global.CcyuwenStore = {
		KINDS: KINDS,
		LEVELS: LEVELS,
		load: load,
		save: save,
		ensureSeed: ensureSeed,
		upsertPoint: upsertPoint,
		removePoint: removePoint,
		buildTodayQueue: buildTodayQueue,
		reviewPoint: reviewPoint,
		stats: stats,
		parseImport: parseImport,
		importPoints: importPoints,
		exportJson: exportJson
	}
})(window)
