<template>
  <div
    class="drag-divider"
    :class="{ 'dragging': isDragging }"
    @mousedown="startDrag"
  >
    <div class="divider-line"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'

const props = defineProps<{
  direction?: 'horizontal' | 'vertical'
  minSize?: number
  maxSize?: number
}>()

const emit = defineEmits<{
  (e: 'drag', delta: number): void
}>()

const isDragging = ref(false)
const lastPos = ref(0)

function startDrag(e: MouseEvent) {
  e.preventDefault()
  isDragging.value = true
  lastPos.value = props.direction === 'horizontal' ? e.clientX : e.clientY

  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
  document.body.style.cursor = props.direction === 'horizontal' ? 'col-resize' : 'row-resize'
  document.body.style.userSelect = 'none'
}

function onDrag(e: MouseEvent) {
  if (!isDragging.value) return

  const currentPos = props.direction === 'horizontal' ? e.clientX : e.clientY
  const delta = currentPos - lastPos.value
  lastPos.value = currentPos

  emit('drag', delta)
}

function stopDrag() {
  isDragging.value = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
}

onUnmounted(() => {
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
})
</script>

<style scoped>
.drag-divider {
  width: 6px;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: col-resize;
  background: transparent;
  flex-shrink: 0;
  position: relative;
  z-index: 10;
}

.drag-divider:hover .divider-line,
.drag-divider.dragging .divider-line {
  background: #6B7B8D;
}

.divider-line {
  width: 1px;
  height: 40px;
  background: #E0DFDC;
  border-radius: 1px;
  transition: background 0.2s;
}

.drag-divider.dragging {
  background: rgba(107, 123, 141, 0.1);
}
</style>