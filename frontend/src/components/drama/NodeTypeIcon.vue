<template>
  <el-icon :class="iconClass">
    <component :is="iconComponent" />
  </el-icon>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  VideoCamera,
  Picture,
  ChatDotRound,
  Star,
  MagicStick,
  User,
  Document,
  Reading,
  Notebook,
  Files,
} from '@element-plus/icons-vue'

const props = defineProps<{
  nodeType: string
  size?: 'small' | 'medium'
}>()

const iconMap: Record<string, unknown> = {
  episode: VideoCamera,
  scene: Picture,
  dialogue: ChatDotRound,
  action: Star,
  effect: MagicStick,
  inner_voice: User,
  section: Document,
  narration: Reading,
  intro: Notebook,
}

const iconComponent = computed(() => iconMap[props.nodeType] || Files)

const iconClass = computed(() => ({
  'node-icon': true,
  [`node-icon--${props.nodeType}`]: true,
  'node-icon--small': props.size === 'small',
}))
</script>

<style scoped>
.node-icon {
  font-size: 14px;
  flex-shrink: 0;
}

.node-icon--small {
  font-size: 12px;
}

.node-icon--episode { color: #6B7B8D; }
.node-icon--scene { color: #8D7B6B; }
.node-icon--dialogue { color: #6B8D7B; }
.node-icon--action { color: #8D8B6B; }
.node-icon--effect { color: #7B6B8D; }
.node-icon--inner_voice { color: #8D6B6B; }
.node-icon--section { color: #6B7B8D; }
.node-icon--narration { color: #6B8D8D; }
.node-icon--intro { color: #8D7B8D; }
</style>
