/**
 * 默写判分
 * @module js/grade
 * @author ccyuwen
 * @version 1.0.0
 * @created 2026-09-02
 */
(function (global) {
	const PUNCT = /[\s，。！？、；：,.!?;:'"“”‘’《》【】（）()\[\]—…·]/g

	/**
	 * 去掉空白和标点，便于古诗对比
	 * @param {string} text
	 * @returns {string}
	 */
	function normalize(text) {
		if (text === null || text === undefined) {
			return ''
		}
		return String(text).replace(PUNCT, '')
	}

	/**
	 * 编辑距离
	 * @param {string} left
	 * @param {string} right
	 * @returns {number}
	 */
	function levenshtein(left, right) {
		const a = left === null || left === undefined ? '' : String(left)
		const b = right === null || right === undefined ? '' : String(right)
		if (a === b) {
			return 0
		}
		if (a.length === 0) {
			return b.length
		}
		if (b.length === 0) {
			return a.length
		}
		const prev = []
		let i = 0
		for (i = 0; i <= b.length; i += 1) {
			prev[i] = i
		}
		for (i = 1; i <= a.length; i += 1) {
			const curr = [i]
			let j = 1
			for (j = 1; j <= b.length; j += 1) {
				const cost = a.charAt(i - 1) === b.charAt(j - 1) ? 0 : 1
				curr[j] = Math.min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost)
			}
			let k = 0
			for (k = 0; k < curr.length; k += 1) {
				prev[k] = curr[k]
			}
		}
		return prev[b.length]
	}

	/**
	 * 逐字对照（按标准答案长度）
	 * @param {string} input
	 * @param {string} expected
	 * @returns {Array<{char: string, ok: boolean}>}
	 */
	function diffChars(input, expected) {
		const typed = normalize(input)
		const answer = normalize(expected)
		return answer.split('').map(function (char, index) {
			return {
				char: char,
				ok: typed.charAt(index) === char
			}
		})
	}

	/**
	 * 自动判分，映射到 SM-2 quality
	 * @param {string} input
	 * @param {string} expected
	 * @returns {{quality: number, ratio: number, correct: boolean, chars: Array}}
	 */
	function gradeAnswer(input, expected) {
		const typed = normalize(input)
		const answer = normalize(expected)
		if (!answer) {
			return { quality: 1, ratio: 0, correct: false, chars: [] }
		}
		if (!typed) {
			return { quality: 1, ratio: 0, correct: false, chars: diffChars('', answer) }
		}
		if (typed === answer) {
			return { quality: 5, ratio: 1, correct: true, chars: diffChars(typed, answer) }
		}
		const distance = levenshtein(typed, answer)
		const ratio = 1 - distance / Math.max(typed.length, answer.length)
		const safeRatio = Math.max(0, Math.round(ratio * 100) / 100)
		let quality = 1
		if (safeRatio >= 0.95) {
			quality = 5
		} else if (safeRatio >= 0.8) {
			quality = 3
		}
		return {
			quality: quality,
			ratio: safeRatio,
			correct: quality === 5,
			chars: diffChars(typed, answer)
		}
	}

	global.CcyuwenGrade = {
		normalize: normalize,
		levenshtein: levenshtein,
		diffChars: diffChars,
		gradeAnswer: gradeAnswer
	}
})(window)
