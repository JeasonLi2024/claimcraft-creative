// 介入编辑草稿 store（Zustand slice）
// 对齐 spec 第 6.7 节 / Task 2.7.1 + 2.7.2
// 编辑草稿使用 sessionStorage 持久化，key 格式：
//   wf_intervention_draft_${runId}_${interventionId}_${revision}
// run / intervention / revision 切换时销毁旧草稿
import { create } from "zustand"
import type { WorkflowIntervention } from "@/types/workflow"

// ---------- sessionStorage 工具 ----------

function buildDraftKey(runId: number, interventionId: number, revision: number): string {
  return `wf_intervention_draft_${runId}_${interventionId}_${revision}`
}

function loadDraft(key: string): Record<string, unknown> | null {
  try {
    const raw = sessionStorage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
    return null
  } catch {
    // JSON 解析失败或 sessionStorage 不可用
    return null
  }
}

function saveDraft(key: string, values: Record<string, unknown>): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(values))
  } catch {
    // quota 超限或 sessionStorage 不可用，静默忽略
  }
}

function clearDraft(key: string): void {
  try {
    sessionStorage.removeItem(key)
  } catch {
    // 忽略
  }
}

// ---------- submit 处理器注入 ----------
//
// intervention 提交 API（submitIntervention）在 Task 3.7 才引入。
// 此处通过外部注入处理器解耦，便于测试 + 渐进接入。

export type InterventionSubmitHandler = (
  intervention: WorkflowIntervention,
  values: Record<string, unknown>,
) => Promise<void>

let submitHandler: InterventionSubmitHandler | null = null

export function configureInterventionSubmitHandler(handler: InterventionSubmitHandler | null): void {
  submitHandler = handler
}

// ---------- store 类型 ----------

export interface InterventionStoreState {
  currentIntervention: WorkflowIntervention | null
  draftValues: Record<string, unknown>
  validationErrors: Record<string, string>
  revisionConflict: { baseRevision: number; currentRevision: number } | null
  isSubmitting: boolean
  /** 内部：当前草稿对应的 sessionStorage key */
  _draftKey: string | null
  /**
   * Task 3.5.2：当前运行的 revision（从 workflow-run-store 同步）。
   * 用于在介入面板上显示「当前运行修订 #N」并与 baseRevision 比对，
   * 当 currentRevision > currentIntervention.base_revision 时视为冲突。
   */
  currentRevision: number | null

  setIntervention: (intervention: WorkflowIntervention | null) => void
  updateDraftValue: (fieldName: string, value: unknown) => void
  resetDraft: () => void
  setValidationError: (fieldName: string, error: string | null) => void
  setRevisionConflict: (conflict: { baseRevision: number; currentRevision: number } | null) => void
  /** Task 3.5.2：从 workflow-run-store.snapshotRevision 同步当前 revision */
  setCurrentRevision: (revision: number | null) => void
  submitDraft: () => Promise<void>
}

// ---------- store 实现 ----------

export const useInterventionStore = create<InterventionStoreState>()((set, get) => ({
  currentIntervention: null,
  draftValues: {},
  validationErrors: {},
  revisionConflict: null,
  isSubmitting: false,
  _draftKey: null,
  currentRevision: null,

  setIntervention: (intervention) => {
    const state = get()
    const oldKey = state._draftKey

    // SubTask 2.7.2: run / intervention / revision 切换时销毁旧草稿
    if (oldKey) {
      if (!intervention) {
        // 切换到 null：清除旧草稿
        clearDraft(oldKey)
      } else {
        const newKey = buildDraftKey(
          intervention.run_id,
          intervention.id,
          intervention.base_revision,
        )
        if (newKey !== oldKey) {
          // 切换到不同 intervention：清除旧草稿
          clearDraft(oldKey)
        }
      }
    }

    if (!intervention) {
      set({
        currentIntervention: null,
        draftValues: {},
        validationErrors: {},
        revisionConflict: null,
        _draftKey: null,
      })
      return
    }

    // 加载新草稿
    const newKey = buildDraftKey(
      intervention.run_id,
      intervention.id,
      intervention.base_revision,
    )
    const loaded = loadDraft(newKey)

    // 初始值来自 intervention.initial_values，再被已存草稿覆盖
    const initialDraft: Record<string, unknown> = {}
    if (intervention.initial_values && typeof intervention.initial_values === "object") {
      Object.assign(initialDraft, intervention.initial_values)
    }
    if (loaded) {
      Object.assign(initialDraft, loaded)
    }

    set({
      currentIntervention: intervention,
      draftValues: initialDraft,
      validationErrors: {},
      revisionConflict: null,
      _draftKey: newKey,
    })
  },

  updateDraftValue: (fieldName, value) => {
    const state = get()
    const newDraft = { ...state.draftValues, [fieldName]: value }
    if (state._draftKey) {
      saveDraft(state._draftKey, newDraft)
    }
    set({ draftValues: newDraft })
  },

  resetDraft: () => {
    const state = get()
    if (state._draftKey) {
      clearDraft(state._draftKey)
    }
    // 重置草稿为 initial_values（若存在）
    const intervention = state.currentIntervention
    const resetValues: Record<string, unknown> = {}
    if (intervention?.initial_values && typeof intervention.initial_values === "object") {
      Object.assign(resetValues, intervention.initial_values)
    }
    set({ draftValues: resetValues, validationErrors: {} })
  },

  setValidationError: (fieldName, error) => {
    set((state) => {
      const next = { ...state.validationErrors }
      if (error == null || error === "") {
        delete next[fieldName]
      } else {
        next[fieldName] = error
      }
      return { validationErrors: next }
    })
  },

  setRevisionConflict: (conflict) => {
    set({ revisionConflict: conflict })
  },

  setCurrentRevision: (revision) => {
    const state = get()
    set({ currentRevision: revision })
    // 自动检测 revision 冲突：当 currentRevision 超过 intervention.base_revision 时
    if (
      revision != null &&
      state.currentIntervention &&
      revision > state.currentIntervention.base_revision
    ) {
      set({
        revisionConflict: {
          baseRevision: state.currentIntervention.base_revision,
          currentRevision: revision,
        },
      })
    } else if (revision == null || !state.currentIntervention) {
      // revision 清空或无 intervention 时清除冲突标记
      if (state.revisionConflict) {
        set({ revisionConflict: null })
      }
    }
  },

  submitDraft: async () => {
    const state = get()
    const intervention = state.currentIntervention
    if (!intervention) {
      throw new Error("没有当前介入记录，无法提交")
    }
    if (state.revisionConflict) {
      throw new Error("存在修订冲突，请关闭面板后重新加载最新数据")
    }
    if (state.isSubmitting) return

    set({ isSubmitting: true })
    try {
      if (submitHandler) {
        await submitHandler(intervention, state.draftValues)
      }
      // 提交成功：清空草稿 + sessionStorage
      if (state._draftKey) {
        clearDraft(state._draftKey)
      }
      set({
        isSubmitting: false,
        draftValues: {},
        validationErrors: {},
        _draftKey: null,
        // 保留 currentIntervention，由父组件决定何时调用 setIntervention(null)
      })
    } catch (e) {
      set({ isSubmitting: false })
      throw e
    }
  },
}))

export default useInterventionStore
