import { createApp } from 'vue'
import { createPinia } from 'pinia'
// Element Plus 按需加载，通过 unplugin-vue-components 自动导入
// 图标已在各组件中按需导入，无需全局注册
import 'element-plus/dist/index.css'
import './styles/main.scss'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 图标已按需导入，移除全局注册以减小包体积

app.use(createPinia())
app.use(router)
// Element Plus 组件通过 unplugin-vue-components 自动注册，无需手动 use

app.mount('#app')
