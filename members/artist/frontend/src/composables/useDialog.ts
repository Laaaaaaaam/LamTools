import { ref } from 'vue'

export interface DialogOptions {
  title?: string
  message: string
  inputLabel?: string
  inputDefault?: string
}

type DialogResolve = (value: string | boolean | null) => void

const visible = ref(false)
const options = ref<DialogOptions>({ message: '' })
const mode = ref<'confirm' | 'alert' | 'prompt'>('alert')
const inputValue = ref('')
let resolver: DialogResolve | null = null
let dialogId = 0

export function useDialog() {
  function _open(m: typeof mode.value, opts: DialogOptions): Promise<string | boolean | null> {
    return new Promise((resolve) => {
      if (resolver) {
        resolver(null)
      }
      const currentId = ++dialogId
      resolver = (value) => {
        if (currentId === dialogId) {
          resolve(value)
        }
      }
      options.value = opts
      mode.value = m
      inputValue.value = opts.inputDefault || ''
      visible.value = true
    })
  }

  function showConfirm(message: string, title?: string): Promise<boolean> {
    return _open('confirm', { message, title }) as Promise<boolean>
  }

  function showAlert(message: string, title?: string): Promise<true> {
    return _open('alert', { message, title }) as Promise<true>
  }

  function showPrompt(message: string, inputLabel?: string, inputDefault?: string): Promise<string | null> {
    return _open('prompt', { message, inputLabel, inputDefault }) as Promise<string | null>
  }

  function confirm() {
    if (mode.value === 'prompt') {
      resolver?.(inputValue.value)
    } else {
      resolver?.(true)
    }
    resolver = null
    visible.value = false
  }

  function cancel() {
    resolver?.(mode.value === 'confirm' ? false : null)
    resolver = null
    visible.value = false
  }

  function close() {
    resolver?.(null)
    resolver = null
    visible.value = false
  }

  return {
    visible,
    options,
    mode,
    inputValue,
    showConfirm,
    showAlert,
    showPrompt,
    confirm,
    cancel,
    close,
  }
}

export const dialog = useDialog()
