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

const routes = [
	{ path: '/login', name: 'Login', component: LoginPage, meta: { public: true, title: '登录' } },
	{ path: '/admin', name: 'Admin', component: AdminPage, meta: { admin: true, title: '资源审核' } },
	{ path: '/materials', name: 'Materials', component: MaterialsPage, meta: { admin: true, title: '原始资料' } },
	{ path: '/points', name: 'Points', component: PointsPage, meta: { title: '知识点' } },
	{ path: '/library', name: 'Library', component: LibraryPage, meta: { title: '知识库' } },
	{ path: '/courses', name: 'Courses', component: CoursesPage, meta: { title: '我的课程' } },
	{ path: '/courses/:id/drill', name: 'Drill', component: DrillPage, meta: { title: '今日默写' } },
	{ path: '/courses/:id/plan', name: 'Plan', component: PlanPage, meta: { title: '学习计划' } },
	{ path: '/courses/:id/stats', name: 'Stats', component: StatsPage, meta: { title: '课程掌握' } },
	{ path: '/coverage', name: 'Coverage', component: CoveragePage, meta: { title: '全库覆盖' } },
	{ path: '/', redirect: '/courses' }
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
		return { name: 'Courses' }
	}
	return true
})

export default router
