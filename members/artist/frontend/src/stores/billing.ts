import { defineStore } from 'pinia'
import { ref } from 'vue'
import { billingApi } from '../api/billing'
import type { BillingSummary } from '../types'

export const useBillingStore = defineStore('billing', () => {
  const summary = ref<BillingSummary>({ today: 0, month: 0, total: 0, currency: 'CNY' })

  async function fetchSummary() {
    try {
      const { data } = await billingApi.summary()
      summary.value = data
    } catch {
      // silently fail
    }
  }

  return { summary, fetchSummary }
})
