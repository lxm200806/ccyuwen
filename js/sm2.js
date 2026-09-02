/**
 * SM-2 间隔重复
 * @module js/sm2
 * @author ccyuwen
 * @version 1.0.0
 * @created 2026-09-02
 */
(function (global) {
	const MIN_EASE = 1.3
	const FIRST_INTERVAL = 1
	const SECOND_INTERVAL = 6

	/**
	 * 把日期字符串加减天数
	 * @param {string} dayText - YYYY-MM-DD
	 * @param {number} dayCount
	 * @returns {string}
	 */
	function addDays(dayText, dayCount) {
		const date = parseDay(dayText)
		date.setDate(date.getDate() + dayCount)
		return formatDay(date)
	}

	/**
	 * @param {string} dayText
	 * @returns {Date}
	 */
	function parseDay(dayText) {
		if (!dayText) {
			return new Date(NaN)
		}
		const parts = String(dayText).split('-')
		if (parts.length !== 3) {
			return new Date(NaN)
		}
		return new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]))
	}

	/**
	 * @param {Date} date
	 * @returns {string}
	 */
	function formatDay(date) {
		if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
			return ''
		}
		const year = date.getFullYear()
		const month = String(date.getMonth() + 1)
		const day = String(date.getDate())
		const mm = month.length < 2 ? '0' + month : month
		const dd = day.length < 2 ? '0' + day : day
		return year + '-' + mm + '-' + dd
	}

	/**
	 * @returns {string}
	 */
	function todayText() {
		return formatDay(new Date())
	}

	/**
	 * 按 SM-2 计算下次复习
	 * @param {{n?: number, ef?: number, interval?: number, lapses?: number}|null} state
	 * @param {number} quality - 0~5，<3 视为失败
	 * @param {string} today
	 * @returns {{n: number, ef: number, interval: number, due: string, lapses: number, last: string}}
	 */
	function schedule(state, quality, today) {
		const safeToday = today || todayText()
		const prev = state && typeof state === 'object' ? state : {}
		let n = Number(prev.n) || 0
		let ef = Number(prev.ef) || 2.5
		let interval = Number(prev.interval) || 0
		let lapses = Number(prev.lapses) || 0
		const score = Number(quality)

		if (!Number.isFinite(score) || score < 3) {
			n = 0
			interval = FIRST_INTERVAL
			lapses += 1
		} else {
			if (n === 0) {
				interval = FIRST_INTERVAL
			} else if (n === 1) {
				interval = SECOND_INTERVAL
			} else {
				interval = Math.round(interval * ef)
				if (interval < 1) {
					interval = 1
				}
			}
			n += 1
			const gap = 5 - score
			ef = ef + (0.1 - gap * (0.08 + gap * 0.02))
			if (ef < MIN_EASE) {
				ef = MIN_EASE
			}
		}

		return {
			n: n,
			ef: Math.round(ef * 100) / 100,
			interval: interval,
			due: addDays(safeToday, interval),
			lapses: lapses,
			last: safeToday
		}
	}

	/**
	 * @param {{interval?: number, n?: number}|null} state
	 * @returns {boolean}
	 */
	function isMastered(state) {
		if (!state) {
			return false
		}
		return Number(state.interval) >= 21 || Number(state.n) >= 5
	}

	global.CcyuwenSm2 = {
		addDays: addDays,
		parseDay: parseDay,
		formatDay: formatDay,
		todayText: todayText,
		schedule: schedule,
		isMastered: isMastered
	}
})(window)
