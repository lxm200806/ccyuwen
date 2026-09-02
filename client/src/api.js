/**
 * REST 封装
 * @module api
 * @author ccyuwen
 * @version 1.0.0
 * @created 2026-09-02
 */

const TOKEN_KEY = 'ccyuwen.token'
const USER_KEY = 'ccyuwen.user'

/**
 * @returns {object|null}
 */
export function getUser() {
	try {
		return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
	} catch (error) {
		return null
	}
}

export function getToken() {
	return localStorage.getItem(TOKEN_KEY) || ''
}

export function setSession(token, user) {
	localStorage.setItem(TOKEN_KEY, token)
	localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
	localStorage.removeItem(TOKEN_KEY)
	localStorage.removeItem(USER_KEY)
}

/**
 * @param {string} path
 * @param {RequestInit} options
 * @returns {Promise<any>}
 */
export async function request(path, options = {}) {
	const headers = Object.assign({}, options.headers || {})
	const token = getToken()
	if (token) {
		headers.Authorization = 'Bearer ' + token
	}
	if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
		headers['Content-Type'] = 'application/json'
	}
	const response = await fetch('/api' + path, Object.assign({}, options, { headers }))
	const data = await response.json().catch(function () {
		return {}
	})
	if (response.status === 401) {
		clearSession()
		if (path !== '/login') {
			window.location.hash = '#/login'
		}
	}
	if (!response.ok) {
		throw new Error(formatDetail(data.detail) || '请求失败')
	}
	return data
}

function formatDetail(detail) {
	if (!detail) {
		return ''
	}
	if (typeof detail === 'string') {
		return detail
	}
	if (Array.isArray(detail)) {
		return detail.map(function (item) {
			return item.msg || JSON.stringify(item)
		}).join('; ')
	}
	return String(detail)
}
