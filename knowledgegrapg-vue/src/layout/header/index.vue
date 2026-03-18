<template>
	<header class="sys-header">
		<div class="sys-logo">
			<span class="sys-title">知识图谱-疾病知识系统</span>
		</div>
	</header>
</template>

<style scoped>
.sys-header {
	width: 100%;
	height: 60px;
	background: #fff;
	display: flex;
	align-items: center;
	justify-content: space-between;
	box-shadow: 0 2px 8px rgba(2, 6, 23, 0.06);
	padding: 0 32px;
}
.sys-logo {
	display: flex;
	align-items: center;
}
.logo-img {
	width: 36px;
	height: 36px;
	margin-right: 12px;
}
.sys-title {
	font-size: 1.5rem;
	font-weight: bold;
	color: #0f172a;
	letter-spacing: 2px;
}
.sys-nav {
	display: flex;
	gap: 32px;
}
.sys-link {
	color: #1f2937; /* gray-800 */
	text-decoration: none;
	font-size: 1.1rem;
	padding: 6px 16px;
	border-radius: 4px;
	transition: background 0.2s, color 0.2s;
}
.sys-link:hover, .sys-link.active {
	background: #eff6ff; /* blue-50 */
	color: #1d4ed8; /* blue-700 */
}
.sys-user {
	display: flex;
	align-items: center;
	gap: 10px;
}
.user-name {
	color: #1f2937;
	font-size: 1rem;
}
.user-avatar {
	width: 32px;
	height: 32px;
	border-radius: 50%;
	border: 2px solid #93c5fd; /* blue-300 */
}
</style>
