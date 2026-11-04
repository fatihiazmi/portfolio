<script setup lang="ts">
// One case study section: a Write / Preview toggle over the same text.
import SelectButton from "primevue/selectbutton";
import Textarea from "primevue/textarea";
import { computed, ref } from "vue";
import { renderMarkdown } from "../markdown";

const props = defineProps<{ id: string; label: string; maxLength: number }>();
const model = defineModel<string>({ required: true });

const modes = ["Write", "Preview"];
const mode = ref("Write");
const html = computed(() => (mode.value === "Preview" ? renderMarkdown(model.value) : ""));
const count = computed(() => `${model.value.length.toLocaleString()} / ${props.maxLength.toLocaleString()}`);
</script>

<template>
  <div class="field">
    <div class="page-head">
      <label :for="id" class="field-label">{{ label }}</label>
      <SelectButton v-model="mode" :options="modes" :allow-empty="false" :aria-label="`${label} view`" />
    </div>
    <Textarea
      v-show="mode === 'Write'"
      :id="id"
      v-model="model"
      class="md-source"
      rows="16"
      :maxlength="maxLength"
      auto-resize
      fluid
    />
    <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown drops raw HTML and unsafe URLs -->
    <div v-if="mode === 'Preview'" class="md-preview" v-html="html || '<p class=muted>Nothing written yet.</p>'" />
    <span class="hint">Markdown. {{ count }} characters.</span>
  </div>
</template>
