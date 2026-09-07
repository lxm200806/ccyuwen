/**
 * 路由
 * @module router
 * @author ccyuwen
 * @version 1.0.0
 * @created 2026-09-02
 */
import { createRouter, createWebHistory } from 'vue-router'
import { getToken, getUser } from './api.js'
import LoginPage from './views/login-page.vue'
import AdminPage from './views/admin-page.vue'
import MaterialsPage from './views/materials-page.vue'
import PointsPage from './views/points-page.vue'
import LibraryPage from './views/library-page.vue'
import CoursesPage from './views/courses-page.vue'
import DrillPage from './views/drill-page.vue'
import PlanPage from './views/plan-page.vue'
import StatsPage from './views/stats-page.vue'
import CoveragePage from './views/coverage-page.vue'
import FamilyPage from './views/family-page.vue'
import WrongBookPage from './views/wrong-book-page.vue'

export function homePath(user) {
	if (user && user.role === 'parent') {
		return '/family'
	}
	if (user && user.role === 'admin') {
		return '/admin'
	}
	return '/courses'
}

const routes = [
	{ path: '/login', name: 'Login', component: LoginPage, meta: { public: true, title: '登录' } },
	{ path: '/family', name: 'Family', component: FamilyPage, meta: { parent: true, title: '家庭' } },
	{ path: '/admin', name: 'Admin', component: AdminPage, meta: { admin: true, title: '资源审核' } },
	{ path: '/materials', name: 'Materials', component: MaterialsPage, meta: { admin: true, title: '原始资料' } },
	{ path: '/points', name: 'Points', component: PointsPage, meta: { student: true, title: '知识点' } },
	{ path: '/library', name: 'Library', component: LibraryPage, meta: { title: '组课' } },
	{ path: '/courses', name: 'Courses', component: CoursesPage, meta: { title: '我的课程' } },
	{ path: '/courses/:id/drill', name: 'Drill', component: DrillPage, meta: { student: true, title: '今日默写' } },
	{ path: '/courses/:id/plan', name: 'Plan', component: PlanPage, meta: { title: '学习计划' } },
	{ path: '/courses/:id/stats', name: 'Stats', component: StatsPage, meta: { title: '课程掌握' } },
	{ path: '/courses/:id/wrong-book', name: 'WrongBook', component: WrongBookPage, meta: { title: '错题再练' } },
	{ path: '/coverage', name: 'Coverage', component: CoveragePage, meta: { student: true, title: '全库覆盖' } },
	{ path: '/', redirect: () => homePath(getUser()) }
]

const router = createRouter({
	history: createWebHistory(),
	routes
})

router.beforeEach((to) => {
	if (to.meta.public) {
		return true
	}
	if (!getToken()) {
		return { name: 'Login' }
	}
	const user = getUser()
	if (to.meta.admin && (!user || user.role !== 'admin')) {
		return { path: homePath(user) }
	}
	if (to.meta.parent && (!user || user.role !== 'parent')) {
		return { path: homePath(user) }
	}
	if (to.meta.student && user && user.role === 'parent') {
		if (to.name === 'Drill') {
			return { name: 'WrongBook', params: { id: to.params.id } }
		}
		return { path: '/family' }
	}
	if (to.name === 'Courses' && user && user.role === 'parent') {
		return { path: '/family' }
	}
	return true
})

export default router
