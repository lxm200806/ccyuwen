/**
 * 类型、级别、年级标签，与服务端 cards.py 对齐。
 */
export const KIND_OPTIONS = [
	{ id: 'poem', label: '古诗' },
	{ id: 'wenyan', label: '文言文' },
	{ id: 'idiom', label: '词语' },
	{ id: 'saying', label: '俗语名句' },
	{ id: 'sentence', label: '优美句子' },
	{ id: 'zi', label: '易错字' }
]

export const KIND_LABEL = {
	poem: '古诗',
	wenyan: '文言文',
	idiom: '词语',
	saying: '俗语名句',
	sentence: '优美句子',
	zi: '易错字'
}

export const LEVEL_OPTIONS = ['L1', 'L2', 'L3', 'L4']

export const LEVEL_LABEL = {
	L1: 'L1 课内必背',
	L2: 'L2 课内拓展',
	L3: 'L3 小升初高频',
	L4: 'L4 竞赛超纲'
}

export const GRADE_OPTIONS = [
	'一年级上',
	'一年级下',
	'二年级上',
	'二年级下',
	'三年级上',
	'三年级下',
	'四年级上',
	'四年级下',
	'五年级上',
	'五年级下',
	'六年级上',
	'六年级下'
]

export function kindLabel(kind) {
	return KIND_LABEL[kind] || kind
}

export function levelLabel(level) {
	return LEVEL_LABEL[level] || level
}

export const QUESTION_TYPE_OPTIONS = [
	{ id: 'dictation', label: '默写' },
	{ id: 'recite', label: '背诵' },
	{ id: 'char_judge', label: '字对错' },
	{ id: 'meaning_choice', label: '理解意思' }
]

export const QUESTION_TYPE_LABEL = {
	dictation: '默写',
	recite: '背诵',
	char_judge: '字对错',
	meaning_choice: '理解意思'
}

export const AUDIENCE_OPTIONS = [
	{ id: 'all', label: '全年级' },
	{ id: 'lower', label: '低年级' },
	{ id: 'upper', label: '高年级' }
]

export const AUDIENCE_LABEL = {
	all: '全年级',
	lower: '低年级',
	upper: '高年级'
}

export function questionTypeLabel(value) {
	return QUESTION_TYPE_LABEL[value] || value || '默写'
}

export function audienceLabel(value) {
	return AUDIENCE_LABEL[value] || value || '全年级'
}
