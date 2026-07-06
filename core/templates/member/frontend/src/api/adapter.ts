import type { ProductAdapter, CoreSessionGroup } from '@lamtools/ui'

export const adapter: ProductAdapter = {
  id: '__MEMBER_ID__',
  displayName: '__DISPLAY_NAME__',
  version: '0.1.0',
  supportedFeatures: ['chat'],
}

export function useSessionGroups() {
  return {
    sessionGroups: [
      { id: '__MEMBER_ID__-sessions', label: '__DISPLAY_NAME__ sessions', description: 'All __DISPLAY_NAME__ sessions' },
    ] as CoreSessionGroup[],
  }
}
