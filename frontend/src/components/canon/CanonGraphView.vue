<template>
  <div class="canon-graph">
    <div class="graph-toolbar">
      <el-select v-model="typeFilter" multiple collapse-tags placeholder="按维度筛选"
                 size="small" style="width: 260px">
        <el-option v-for="t in ENTITY_TYPES" :key="t" :label="TYPE_LABEL[t]" :value="t" />
      </el-select>
      <el-button size="small" @click="reload">刷新</el-button>
      <el-text type="info" size="small">{{ nodeCount }} 节点 · {{ edgeCount }} 关系</el-text>
    </div>
    <el-empty v-if="!loading && edgeCount === 0 && nodeCount === 0"
              description="尚无图谱，请先在列表视图提取设定" />
    <RelationGraph v-else ref="graphRef" :options="graphOptions"
                   @node-click="onNodeClick" @line-click="onLineClick" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import RelationGraph from 'relation-graph-vue3'
import { canonApi, type CanonEntityType, type CanonGraph } from '@/api/canon'

const props = defineProps<{ referenceId: number }>()
const emit = defineEmits<{ (e: 'select-node', id: number): void
                          (e: 'select-edge', id: number): void }>()

const ENTITY_TYPES: CanonEntityType[] = ['character','location','ability','faction',
  'worldrule','event','item','race','realm','concept']
const TYPE_LABEL: Record<CanonEntityType, string> = {
  character:'角色', location:'地点', ability:'能力', faction:'势力', worldrule:'世界观规则',
  event:'事件', item:'物品', race:'种族血脉', realm:'境界体系', concept:'专有术语' }
const TYPE_COLOR: Record<CanonEntityType, string> = {
  character:'#5B8FF9', location:'#5AD8A6', ability:'#F6BD16', faction:'#E8684A',
  worldrule:'#9270CA', event:'#FF9D4D', item:'#269A99', race:'#FF99C3',
  realm:'#6DC8EC', concept:'#A6A6A6' }

const graphRef = ref()
const loading = ref(false)
const raw = ref<CanonGraph>({ nodes: [], edges: [] })
const typeFilter = ref<CanonEntityType[]>([])
const graphOptions = reactive({ defaultLineShape: 1, defaultJunctionPoint: 'border',
  defaultNodeShape: 0, layouts: [{ layoutName: 'force' }] })

const nodeCount = computed(() => visibleNodes().length)
const edgeCount = computed(() => raw.value.edges.length)

function visibleNodes() {
  if (typeFilter.value.length === 0) return raw.value.nodes
  return raw.value.nodes.filter(n => typeFilter.value.includes(n.entity_type))
}

function buildGraphJson() {
  const visIds = new Set(visibleNodes().map(n => n.id))
  const nodes = visibleNodes().map(n => ({
    id: String(n.id), text: n.canonical_name, color: TYPE_COLOR[n.entity_type],
    nodeShape: 0,
    width: n.importance === 'critical' ? 70 : n.importance === 'major' ? 56 : 44,
  }))
  const lines = raw.value.edges
    .filter(e => visIds.has(e.source_entity_id) && visIds.has(e.target_entity_id))
    .map(e => ({ from: String(e.source_entity_id), to: String(e.target_entity_id),
                 text: e.label || e.relation_type, _rid: e.id }))
  return { rootId: nodes[0]?.id, nodes, lines }
}

async function render() {
  const inst = graphRef.value?.getInstance?.()
  if (inst) await inst.setJsonData(buildGraphJson())
}

async function reload() {
  loading.value = true
  try {
    const { data } = await canonApi.getGraph(props.referenceId)
    raw.value = data
    await render()
  } finally { loading.value = false }
}

function onNodeClick(node: any) { emit('select-node', Number(node.id)); return false }
function onLineClick(line: any, link: any) {
  const rid = link?.relations?.[0]?._rid ?? line?._rid
  if (rid != null) emit('select-edge', Number(rid)); return false
}

watch(typeFilter, render)
onMounted(reload)
defineExpose({ reload })
</script>

<style scoped>
.canon-graph { display: flex; flex-direction: column; height: 70vh; }
.graph-toolbar { display: flex; gap: 12px; align-items: center; padding: 8px 0; }
.canon-graph :deep(.rel-map) { flex: 1; min-height: 0; }
</style>
