/**
 * UI Core — Public API
 * Exports all components, composables, helpers, and types
 */

// Types
export type {
  ProductFeatureId,
  ProductAdapter,
  CoreSessionGroup,
  CoreRuntimeStepStatus,
  CoreRuntimeStep,
  CoreRuntimeStepGroup,
  SettingsSectionDef,
  CoreApiMapper,
  CoreSessionListItem,
  CoreMessage,
  CoreAttachmentStatus,
  CoreAttachment,
  CoreAttachmentInputItem,
  CoreCommandSource,
  CoreCommandAction,
  CoreCommandCatalogItem,
  CoreCommandToken,
  CoreInputItem,
  CoreModelInputCapabilities,
  CoreSkillInputItem,
  MessagePartType,
  MessagePartStatus,
  MessagePart,
  CoreRuntimeEvent,
  CoreComposerPayload,
  CoreMemberDescriptor,
  WorkspaceSlotName,
  MemberSlotSet,
  SlotValidationResult,
  SessionItem,
  ProjectGroup,
  ThemeStop,
  ThemeArea,
  ThemeData,
  ThemePreset,
  ThemeCSSVars,
} from './types';

export { WORKSPACE_SLOT_NAMES } from './types';

// Components
export { default as WorkspaceShell } from './components/WorkspaceShell.vue';
export { default as SessionSidebar } from './components/SessionSidebar.vue';
export { default as ChatThread } from './components/ChatThread.vue';
export { default as ComposerBar } from './components/ComposerBar.vue';
export { default as CommandPalette } from './components/CommandPalette.vue';
export { default as AttachmentTray } from './components/AttachmentTray.vue';
export { default as RuntimePanel } from './components/RuntimePanel.vue';
export { default as SettingsShell } from './components/SettingsShell.vue';
export { default as ThemeEditor } from './components/ThemeEditor.vue';
export { default as ThemeAreaEditor } from './components/ThemeAreaEditor.vue';

// Helpers
export {
  createSessionMapper,
  createMessageMapper,
  createLoadingStepGroup,
  createProductAdapter,
  createMemberSessionGroup,
  type CoreSessionRawLike,
  type CoreMessageRawLike,
  type CreateSessionMapperOptions,
  type CreateMessageMapperOptions,
} from './helpers';

export {
  DEFAULT_THEME,
  clampNumber,
  normalizeColor,
  rgbaFromHex,
  normalizeGradientStops,
  gradientFromStops,
  gradientFromThemeColors,
  normalizeTheme,
  themeToCSSVars,
  addGradientStop,
  removeGradientStop,
  sortGradientStops,
} from './helpers/theme';

// Data
export { THEME_PRESETS, THEME_PRESET_GROUPS } from './data/theme-presets';
export { PROVIDER_PRESETS } from './data/provider-presets';
export type { ProviderPreset, ProviderPresetModel } from './data/provider-presets';

// Composables
export {
  useCoreWorkbenchController,
  type CoreWorkbenchApi,
  type UseCoreWorkbenchControllerContext,
  type UseCoreWorkbenchControllerOptions,
} from './composables';

export { usePendingAttachments } from './composables/usePendingAttachments';
export { useComposerCommandPalette } from './composables/useComposerCommandPalette';

export {
  useShellLayout,
  type DensityMode,
  type ShellLayoutOptions,
} from './composables/useShellLayout';

export { useTheme } from './composables/useTheme';

export {
  parseComposerSyntax,
  findActiveSlashCandidate,
  type ComposerSyntaxKind,
  type ComposerSyntaxSpan,
} from './composer/syntax';

// Styles
import './styles/variables.css';
import './styles/base.css';
import './styles/layout.css';
import './styles/theme-editor.css';
