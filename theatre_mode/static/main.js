const overlay = document.getElementById('theatreOverlay')
const dialogueText = document.getElementById('dialogueText')
const innerVoiceLayer = document.getElementById('innerVoiceLayer')
const stageText = document.getElementById('stageText')
const heartFill = document.getElementById('heartFill')
const statsValue = document.getElementById('statsValue')
const sceneForm = document.getElementById('sceneForm')
const userInput = document.getElementById('userInput')
const submitButton = document.getElementById('submitButton')
const toggleOverlayButton = document.getElementById('toggleOverlayButton')

const TYPE_SPEED_MS = 80
let currentTypewriterToken = 0
window.lanlan_config = window.lanlan_config || { lanlan_name: '' }
window.cubism4Model = window.cubism4Model || ''
window.vrmModel = window.vrmModel || ''
window.mmdModel = window.mmdModel || ''
window.neko = window.neko || {}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `HTTP ${response.status}`)
  }
  return response.json()
}

function getLanlanNameFromUrl() {
  const url = new URL(window.location.href)
  return url.searchParams.get('lanlan_name') || ''
}

async function bootstrapModelConfig() {
  const lanlanName = getLanlanNameFromUrl()
  const apiUrl = lanlanName
    ? `/api/config/page_config?lanlan_name=${encodeURIComponent(lanlanName)}`
    : '/api/config/page_config'
  try {
    const data = await fetchJson(apiUrl)
    if (!data.success) {
      throw new Error(data.error || '加载页面配置失败')
    }
    const modelPath = String(data.model_path || '')
    window.lanlan_config = {
      ...(window.lanlan_config || {}),
      lanlan_name: lanlanName || data.lanlan_name || '',
      model_type: 'live2d',
      live3d_sub_type: '',
    }
    window.cubism4Model = modelPath
    window.vrmModel = ''
    window.mmdModel = ''

    const live2dContainer = document.getElementById('live2d-container')
    if (live2dContainer) {
      live2dContainer.style.display = 'block'
      live2dContainer.style.visibility = 'visible'
    }
    document.title = `${window.lanlan_config.lanlan_name || 'N.E.K.O.'} Theatre`
    return true
  } catch (error) {
    console.error('[Theatre] 模型配置加载失败:', error)
    const live2dContainer = document.getElementById('live2d-container')
    if (live2dContainer) {
      live2dContainer.style.display = 'block'
      live2dContainer.style.visibility = 'visible'
    }
    return false
  }
}

window.pageConfigReady = bootstrapModelConfig()

async function getPluginId() {
  const pathMatch = window.location.pathname.match(/\/plugin\/([^/]+)\/ui/i)
  if (pathMatch) return decodeURIComponent(pathMatch[1])
  return 'theatre_mode'
}

async function callPluginEntry(entryId, args) {
  const pluginId = await getPluginId()
  const candidates = [
    `/plugin/${encodeURIComponent(pluginId)}/entries/${encodeURIComponent(entryId)}/run`,
    `/plugins/${encodeURIComponent(pluginId)}/entries/${encodeURIComponent(entryId)}/run`,
    `/api/plugins/${encodeURIComponent(pluginId)}/entries/${encodeURIComponent(entryId)}/run`,
  ]
  let lastError = null
  for (const url of candidates) {
    try {
      return await fetchJson(url, {
        method: 'POST',
        body: JSON.stringify(args || {}),
      })
    } catch (error) {
      lastError = error
    }
  }
  throw lastError || new Error('无法调用插件入口')
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

async function typewrite(text) {
  const token = ++currentTypewriterToken
  dialogueText.textContent = ''
  const content = String(text || '')
  for (let i = 0; i < content.length; i += 1) {
    if (token !== currentTypewriterToken) return
    dialogueText.textContent += content[i]
    await sleep(TYPE_SPEED_MS)
  }
}

function setInnerVoice(text) {
  innerVoiceLayer.textContent = text || ''
  if (!text) {
    innerVoiceLayer.classList.remove('show')
    return
  }
  innerVoiceLayer.classList.remove('show')
  requestAnimationFrame(() => {
    innerVoiceLayer.classList.add('show')
    window.setTimeout(() => {
      innerVoiceLayer.classList.remove('show')
    }, 4200)
  })
}

function updateStats(stats = {}) {
  const affection = Math.max(0, Math.min(100, Number(stats.affection || 0)))
  const mood = Number(stats.mood || 0)
  heartFill.style.width = `${affection}%`
  statsValue.textContent = `${affection} / mood ${mood}`
}

window.neko.dispatchMotion = function dispatchMotion(motion, expression, stage = {}) {
  const resolvedMotion = motion || stage.motion || 'Idle'
  const resolvedExpression = expression || stage.expression || 'neutral'
  if (window.LanLan1 && typeof window.LanLan1.playMotion === 'function') {
    window.LanLan1.playMotion(resolvedMotion, 0, 3)
  }
  if (window.LanLan1 && typeof window.LanLan1.setEmotion === 'function') {
    window.LanLan1.setEmotion(resolvedExpression)
  }
}

function renderScene(scene) {
  const stage = scene.stage_directions || {}
  stageText.textContent = `motion: ${stage.motion || 'Idle'} · expression: ${stage.expression || 'neutral'} · bgm: ${stage.bgm || 'default_theatre'}`
  setInnerVoice(scene.inner_voice || '')
  updateStats(scene.stats || {})
  window.neko.dispatchMotion(stage.motion, stage.expression, stage)
  typewrite(scene.dialogue || '')
}

sceneForm.addEventListener('submit', async event => {
  event.preventDefault()
  const value = String(userInput.value || '').trim()
  if (!value) return
  submitButton.disabled = true
  try {
    const result = await callPluginEntry('run_theatre_scene', {
      user_input: value,
      push_to_main: false,
    })
    const scene = result?.scene || result?.value?.scene || result?.data?.scene
    if (!scene) throw new Error('插件未返回 scene')
    renderScene(scene)
  } catch (error) {
    dialogueText.textContent = `生成失败：${error.message || error}`
  } finally {
    submitButton.disabled = false
  }
})

toggleOverlayButton.addEventListener('click', () => {
  overlay.classList.toggle('visible')
})

window.pageConfigReady.finally(() => {
  renderScene({
    type: 'gal_theatre_scene',
    dialogue: '夜色像薄薄的绸缎落下来，我站在光与影的边缘，等你先开口。',
    inner_voice: '如果他愿意再靠近一点，这一幕就能写得更温柔吧。',
    stage_directions: {
      motion: 'Idle',
      expression: 'neutral',
      bgm: 'default_theatre',
    },
    stats: {
      affection: 50,
      mood: 0,
    },
  })
})
