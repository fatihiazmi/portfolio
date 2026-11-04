<script setup lang="ts">
// Images of one project. Edit alt, caption, scrubbed, and order in the table, then
// Save changes sends one PATCH per changed image. Uploads and removals apply at once.
import Button from "primevue/button";
import Column from "primevue/column";
import DataTable, { type DataTableRowReorderEvent } from "primevue/datatable";
import Dialog from "primevue/dialog";
import InputText from "primevue/inputtext";
import Message from "primevue/message";
import Select from "primevue/select";
import ToggleSwitch from "primevue/toggleswitch";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router";
import { api, errorText } from "../api";
import { refreshSummary } from "../store";
import type { AdminImage, AdminProject, ImagePatch } from "../types";

interface Row {
  id: number;
  url: string;
  alt: string;
  caption: string;
  scrubbed: boolean;
}

const route = useRoute();
const router = useRouter();
const toast = useToast();
const confirm = useConfirm();

const projects = ref<AdminProject[]>([]);
const projectId = ref<number | null>(null);
const rows = ref<Row[]>([]);
const saved = ref<Row[]>([]);
const loading = ref(true);
const saving = ref(false);
const error = ref<string | null>(null);

const project = computed(() => projects.value.find((p) => p.id === projectId.value) ?? null);
const options = computed(() =>
  projects.value.map((p) => {
    const open = p.images.filter((i) => !i.scrubbed).length;
    const state = p.published ? "published" : "draft";
    return {
      id: p.id,
      label: `${p.title} · ${state} · ${p.images.length} images${open ? ` · ${open} unscrubbed` : ""}`,
    };
  }),
);
const orderChanged = computed(() => rows.value.some((r, i) => r.id !== saved.value[i]?.id));
const changed = computed(() => {
  const before = new Map(saved.value.map((r) => [r.id, r]));
  return rows.value.filter((r) => {
    const b = before.get(r.id);
    return !b || b.alt !== r.alt || b.caption !== r.caption || b.scrubbed !== r.scrubbed;
  });
});
const dirty = computed(() => orderChanged.value || changed.value.length > 0);
const missingAlt = computed(() => rows.value.some((r) => r.alt.trim() === ""));
const unscrubbed = computed(() => rows.value.filter((r) => !r.scrubbed).length);

function toRow(i: AdminImage): Row {
  return { id: i.id, url: i.url, alt: i.alt, caption: i.caption ?? "", scrubbed: i.scrubbed };
}

function show(id: number | null): void {
  projectId.value = id;
  const images = projects.value.find((p) => p.id === id)?.images ?? [];
  rows.value = images.map(toRow);
  saved.value = images.map(toRow);
}

async function load(keep: number | null): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    projects.value = (await api.projects()).projects;
    const wanted = keep ?? Number(route.query.project);
    const first = projects.value.find((p) => p.images.some((i) => !i.scrubbed && p.published));
    const pick = projects.value.some((p) => p.id === wanted) ? wanted : (first ?? projects.value[0])?.id;
    show(pick ?? null);
  } catch (err) {
    error.value = errorText(err);
  } finally {
    loading.value = false;
  }
}

function pickProject(id: number): void {
  if (id === projectId.value) return;
  if (dirty.value && !window.confirm("The image changes are not saved. Switch project anyway?")) return;
  show(id);
  void router.replace({ query: { project: id } });
}

function onReorder(event: DataTableRowReorderEvent): void {
  rows.value = event.value as Row[];
}

async function save(): Promise<void> {
  saving.value = true;
  const before = new Map(saved.value.map((r) => [r.id, r]));
  const failures: string[] = [];
  for (const [index, row] of rows.value.entries()) {
    const b = before.get(row.id);
    const patch: ImagePatch = {};
    if (b?.alt !== row.alt) patch.alt = row.alt.trim();
    if (b?.caption !== row.caption) patch.caption = row.caption.trim();
    if (b?.scrubbed !== row.scrubbed) patch.scrubbed = row.scrubbed;
    if (orderChanged.value) patch.sort_order = (index + 1) * 10;
    if (Object.keys(patch).length === 0) continue;
    try {
      await api.updateImage(row.id, patch);
    } catch (err) {
      failures.push(`Image "${row.alt || row.id}": ${errorText(err)}`);
    }
  }
  saving.value = false;
  const keep = projectId.value;
  // Reload so the table shows what the server holds, failed rows included.
  if (failures.length === 0) {
    toast.add({ severity: "success", summary: "Images saved", life: 3000 });
    await load(keep);
  } else {
    toast.add({ severity: "error", summary: "Some changes were not saved", detail: failures.join("\n") });
  }
  void refreshSummary();
}

function discard(): void {
  rows.value = saved.value.map((r) => ({ ...r }));
}

function remove(row: Row): void {
  confirm.require({
    header: "Remove image",
    message: `Remove "${row.alt}"? The file is deleted from R2.`,
    rejectProps: { label: "Cancel", severity: "secondary", outlined: true },
    acceptProps: { label: "Remove", severity: "danger" },
    accept: async () => {
      try {
        await api.deleteImage(row.id);
        rows.value = rows.value.filter((r) => r.id !== row.id);
        saved.value = saved.value.filter((r) => r.id !== row.id);
        const p = project.value;
        if (p) p.images = p.images.filter((i) => i.id !== row.id);
        void refreshSummary();
      } catch (err) {
        toast.add({ severity: "error", summary: "Image not removed", detail: errorText(err) });
      }
    },
  });
}

// --- Upload ---

const uploadOpen = ref(false);
const uploading = ref(false);
const uploadError = ref<string | null>(null);
const file = ref<File | null>(null);
const preview = ref<string | null>(null);
const newAlt = ref("");
const newCaption = ref("");
const fileInput = ref<HTMLInputElement | null>(null);

function clearPreview(): void {
  if (preview.value) URL.revokeObjectURL(preview.value);
  preview.value = null;
}

function onFile(event: Event): void {
  const input = event.target as HTMLInputElement;
  const picked = input.files?.[0] ?? null;
  input.value = "";
  if (!picked) return;
  clearPreview();
  file.value = picked;
  preview.value = URL.createObjectURL(picked);
  newAlt.value = "";
  newCaption.value = "";
  uploadError.value = null;
  uploadOpen.value = true;
}

function closeUpload(): void {
  uploadOpen.value = false;
  file.value = null;
  clearPreview();
}

async function upload(): Promise<void> {
  const p = project.value;
  if (!p || !file.value) return;
  uploading.value = true;
  uploadError.value = null;
  try {
    const image = await api.uploadImage(p.id, file.value, newAlt.value.trim(), newCaption.value);
    rows.value = [...rows.value, toRow(image)];
    saved.value = [...saved.value, toRow(image)];
    p.images = [...p.images, image];
    toast.add({ severity: "success", summary: "Image uploaded", detail: "Review it, then mark it scrubbed.", life: 4000 });
    closeUpload();
    void refreshSummary();
  } catch (err) {
    uploadError.value = errorText(err);
  } finally {
    uploading.value = false;
  }
}

onBeforeRouteLeave(() =>
  dirty.value ? window.confirm("The image changes are not saved. Leave anyway?") : true,
);
onBeforeUnmount(clearPreview);
onMounted(() => load(null));
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div class="page-title">
        <h1>Images</h1>
        <p class="page-sub">
          Open each image full size and check it by eye for names, emails, phone numbers, and client data.
          Then switch on Scrubbed. Drag rows by the handle to set the display order.
        </p>
      </div>
      <div class="actions">
        <template v-if="dirty">
          <Button label="Discard" severity="secondary" outlined @click="discard" />
          <Button
            label="Save changes"
            icon="pi pi-check"
            :loading="saving"
            :disabled="missingAlt"
            @click="save"
          />
        </template>
      </div>
    </div>
    <p v-if="error" class="panel warn" role="alert">{{ error }}</p>

    <div v-if="!loading && projects.length === 0" class="panel empty">
      No projects yet. <RouterLink :to="{ name: 'project-new' }">Create one</RouterLink> first.
    </div>

    <template v-if="project">
      <div class="panel" style="flex-direction: row; flex-wrap: wrap; align-items: flex-end">
        <div class="field" style="flex: 1 1 320px">
          <label for="i-project">Project</label>
          <Select
            :model-value="projectId"
            :options="options"
            option-label="label"
            option-value="id"
            input-id="i-project"
            fluid
            @update:model-value="pickProject"
          />
        </div>
        <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="onFile" />
        <Button label="Upload image" icon="pi pi-upload" @click="fileInput?.click()" />
      </div>

      <Message v-if="project.published && unscrubbed" severity="warn" :closable="false">
        Unscrubbed images on this published project: {{ unscrubbed }}. Publish stays blocked until each one is
        checked for personal data and marked scrubbed.
      </Message>
      <Message v-if="missingAlt" severity="error" :closable="false">Every image needs alt text.</Message>

      <div class="panel flush">
        <DataTable :value="rows" data-key="id" :loading="loading" @row-reorder="onReorder">
          <template #empty><div class="empty">No images on this project yet.</div></template>
          <Column row-reorder header-style="width: 3rem" />
          <Column header="Image" style="width: 140px">
            <template #body="{ data }">
              <a :href="data.url" target="_blank" rel="noopener" :aria-label="`Open ${data.alt || 'image'} full size`">
                <img :src="data.url" alt="" class="thumb" :class="{ 'thumb-unscrubbed': !data.scrubbed }" loading="lazy" />
              </a>
            </template>
          </Column>
          <Column header="Alt text and caption">
            <template #body="{ data }">
              <div class="field" style="gap: 8px; min-width: 240px">
                <InputText
                  v-model="data.alt"
                  maxlength="300"
                  :invalid="data.alt.trim() === ''"
                  :aria-label="`Alt text for image ${data.id}`"
                  placeholder="Alt text (required)"
                  fluid
                />
                <InputText
                  v-model="data.caption"
                  maxlength="500"
                  :aria-label="`Caption for image ${data.id}`"
                  placeholder="Caption"
                  fluid
                />
              </div>
            </template>
          </Column>
          <Column header="Scrubbed" style="width: 120px">
            <template #body="{ data }">
              <ToggleSwitch v-model="data.scrubbed" :aria-label="`Scrubbed: image ${data.id}`" />
            </template>
          </Column>
          <Column style="width: 64px">
            <template #body="{ data }">
              <Button
                icon="pi pi-trash"
                severity="danger"
                text
                :aria-label="`Remove image ${data.id}`"
                @click="remove(data)"
              />
            </template>
          </Column>
        </DataTable>
      </div>
    </template>

    <Dialog
      :visible="uploadOpen"
      modal
      header="Upload image"
      :style="{ width: 'min(520px, calc(100vw - 32px))' }"
      @update:visible="closeUpload"
    >
      <div class="field" style="gap: 12px">
        <img v-if="preview" :src="preview" alt="Preview of the chosen file" style="max-width: 100%; max-height: 260px; object-fit: contain; border-radius: 6px" />
        <span class="hint">{{ file?.name }}. PNG, JPEG, or WebP, 5 MB max. It starts unscrubbed.</span>
        <div class="field">
          <label for="u-alt">Alt text</label>
          <InputText id="u-alt" v-model="newAlt" maxlength="300" fluid />
        </div>
        <div class="field">
          <label for="u-caption">Caption</label>
          <InputText id="u-caption" v-model="newCaption" maxlength="500" fluid />
        </div>
        <Message v-if="uploadError" severity="error" :closable="false">{{ uploadError }}</Message>
      </div>
      <template #footer>
        <Button label="Cancel" severity="secondary" outlined @click="closeUpload" />
        <Button label="Upload" icon="pi pi-upload" :loading="uploading" :disabled="newAlt.trim() === ''" @click="upload" />
      </template>
    </Dialog>
  </div>
</template>
