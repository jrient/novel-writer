import { createApp } from 'vue'
import { createPinia } from 'pinia'
// Element Plus 按需加载，通过 unplugin-vue-components 自动导入
// 只需手动导入图标和样式
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import './styles/main.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
// Element Plus 组件通过 unplugin-vue-components 自动注册，无需手动 use

app.mount('#app')
