/**
 * Node 自检：无浏览器时跑核心逻辑
 * @module tests/run-check
 * @author ccyuwen
 * @version 1.0.0
 * @created 2026-09-02
 */
const fs = require('fs')
const path = require('path')
const vm = require('vm')

const root = path.join(__dirname, '..')
const memory = {}
const localStorage = {
	getItem: function (key) {
		return Object.prototype.hasOwnProperty.call(memory, key) ? memory[key] : null
	},
	setItem: function (key, value) {
		memory[key] = String(value)
	},
	removeItem: function (key) {
		delete memory[key]
	}
}
const window = { localStorage: localStorage }
window.window = window
const context = { window: window, localStorage: localStorage }
vm.createContext(context)

function loadScript(rel) {
	const code = fs.readFileSync(path.join(root, rel), 'utf8')
	vm.runInContext(code, context)
}

loadScript('js/sm2.js')
loadScript('js/grade.js')
loadScript('js/seed.js')
loadScript('js/store.js')

const sm2 = context.window.CcyuwenSm2
const grade = context.window.CcyuwenGrade
const store = context.window.CcyuwenStore
const seed = context.window.CcyuwenSeed

let failed = 0
function assert(name, cond) {
	if (cond) {
		console.log('PASS  ' + name)
	} else {
		failed += 1
		console.log('FAIL  ' + name)
	}
}

assert('normalize 去掉标点', grade.normalize('床前明月 光，') === '床前明月光')
assert('normalize 空值', grade.normalize(null) === '' && grade.normalize(undefined) === '')
assert('完全正确 quality=5', grade.gradeAnswer('床前明月光，疑是地上霜。举头望明月，低头思故乡。', '床前明月光，疑是地上霜。举头望明月，低头思故乡。').quality === 5)
assert('空答案 quality=1', grade.gradeAnswer('', '己').quality === 1)
assert('空标准答案', grade.gradeAnswer('己', '').quality === 1)
assert('错一字成语失败', grade.gradeAnswer('守株侍兔', '守株待兔').quality === 1)
assert('编辑距离相同为0', grade.levenshtein('己', '己') === 0)
assert('编辑距离空到字', grade.levenshtein('', '己') === 1)

const first = sm2.schedule(null, 5, '2026-09-02')
assert('新卡全对间隔1天', first.n === 1 && first.interval === 1 && first.due === '2026-09-03')
const second = sm2.schedule(first, 5, '2026-09-03')
assert('第二次全对间隔6天', second.n === 2 && second.interval === 6 && second.due === '2026-09-09')
const third = sm2.schedule(second, 5, '2026-09-09')
assert('第三次按易度拉长', third.n === 3 && third.interval === Math.round(6 * second.ef))
const fail = sm2.schedule(third, 1, '2026-09-20')
assert('失败重置', fail.n === 0 && fail.interval === 1 && fail.lapses === 1)
assert('无效分数当失败', sm2.schedule(first, NaN, '2026-09-02').n === 0)
assert('掌握判定', sm2.isMastered({ interval: 21, n: 4 }) === true)
assert('未掌握', sm2.isMastered({ interval: 6, n: 2 }) === false)
assert('空状态未掌握', sm2.isMastered(null) === false)
assert('日期加减', sm2.addDays('2026-09-02', 6) === '2026-09-08')
assert('坏日期', sm2.formatDay(sm2.parseDay('bad')) === '')

localStorage.removeItem('ccyuwen.v1')
const seeded = store.ensureSeed()
assert('种子写入', seeded.points.length === seed.points.length)
assert('缺字段导入跳过', store.parseImport('[{}]').skip === 1)
assert('空导入', store.parseImport('').ok.length === 0)
const csv = store.parseImport('kind,level,prompt,answer,tags,source\npoem,L3,欲穷千里目，______。,更上一层楼,名句,真题')
assert('CSV 导入', csv.ok.length === 1 && csv.ok[0].answer === '更上一层楼')
const backup = store.parseImport('{"points":[{"kind":"zi","level":"L1","prompt":"写：己","answer":"己"}],"reviews":{"x":{"n":1}}}')
assert('备份 JSON 导入', backup.ok.length === 1 && backup.reviews.x.n === 1)
assert('坏 JSON 导入', store.parseImport('{bad').ok.length === 0)
const added = store.importPoints(csv.ok)
assert('导入去重或新增', added >= 0)
assert('今日队列有卡片', store.buildTodayQueue('2026-09-02').length > 0)
assert('复习回写', !!store.reviewPoint(seeded.points[0].id, 5, '2026-09-02'))
assert('删不存在', store.removePoint('no-such-id') === false)
assert('upsert 拒绝空题', store.upsertPoint({ prompt: '', answer: 'x' }) === null)

if (failed > 0) {
	console.log('失败 ' + failed + ' 项')
	process.exit(1)
}
console.log('全部通过')
