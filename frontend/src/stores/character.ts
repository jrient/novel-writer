import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getCharacters,
  createCharacter,
  updateCharacter,
  deleteCharacter,
} from '@/api/character'
import type { Character, CreateCharacterData, UpdateCharacterData } from '@/api/character'

export const useCharacterStore = defineStore('character', () => {
  const characters = ref<Character[]>([])
  const currentCharacter = ref<Character | null>(null)
  const loading = ref(false)

  async function fetchCharacters(projectId: number, roleType?: string) {
    loading.value = true
    try {
      characters.value = await getCharacters(projectId, roleType)
    } finally {
      loading.value = false
    }
  }

  async function createNewCharacter(projectId: number, data: CreateCharacterData) {
    const character = await createCharacter(projectId, data)
    characters.value.push(character)
    return character
  }

  async function updateCurrentCharacter(projectId: number, characterId: number, data: UpdateCharacterData) {
    const updated = await updateCharacter(projectId, characterId, data)
    const index = characters.value.findIndex(c => c.id === characterId)
    if (index !== -1) {
      characters.value[index] = updated
    }
    if (currentCharacter.value?.id === characterId) {
      currentCharacter.value = updated
    }
    return updated
  }

  async function removeCharacter(projectId: number, characterId: number) {
    await deleteCharacter(projectId, characterId)
    characters.value = characters.value.filter(c => c.id !== characterId)
    if (currentCharacter.value?.id === characterId) {
      currentCharacter.value = null
    }
  }

  function setCurrentCharacter(character: Character | null) {
    currentCharacter.value = character
  }

  return {
    characters,
    currentCharacter,
    loading,
    fetchCharacters,
    createNewCharacter,
    updateCurrentCharacter,
    removeCharacter,
    setCurrentCharacter,
  }
})