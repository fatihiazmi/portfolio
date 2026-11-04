<script setup lang="ts">
// Create or edit one project. One Save button sends the whole form.
import AutoComplete from "primevue/autocomplete";
import Button from "primevue/button";
import InputNumber from "primevue/inputnumber";
import InputText from "primevue/inputtext";
import Message from "primevue/message";
import SelectButton from "primevue/selectbutton";
import Tab from "primevue/tab";
import TabList from "primevue/tablist";
import TabPanel from "primevue/tabpanel";
import TabPanels from "primevue/tabpanels";
import Tabs from "primevue/tabs";
import Textarea from "primevue/textarea";
import ToggleSwitch from "primevue/toggleswitch";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";
import { computed, reactive, ref, watch } from "vue";
import { onBeforeRouteLeave, useRouter } from "vue-router";
import { api, errorText } from "../api";
import MarkdownField from "../components/MarkdownField.vue";
import type { AdminProject, ProjectInput, ProjectKind } from "../types";

const props = defineProps<{ id?: number }>();
const router = useRouter();
const toast = useToast();
const confirm = useConfirm();

// Limits from `api/src/portfolio_api/admin_projects.py`.
const MD_MAX = 20_000;
const SECTIONS = [
  { key: "problem_md", label: "Problem" },
  { key: "built_md", label: "What I built" },
  { key: "decisions_md", label: "Key decisions" },
  { key: "outcome_md", label: "Outcome" },
] as const;
const KINDS: ProjectKind[] = ["client", "personal"];

interface Form {
  slug: string;
  title: string;
  client: string;
  kind: ProjectKind;
  year: number | null;
  summary: string;
  problem_md: string;
  built_md: string;
  decisions_md: string;
  outcome_md: string;
  stack: string[];
  repo_url: string;
  map_x: number | null;
  map_z: number | null;
  published: boolean;
}

function emptyForm(): Form {
  return {
    slug: "",
    title: "",
    client: "",
    kind: "client",
    year: new Date().getFullYear(),
    summary: "",
    problem_md: "",
    built_md: "",
    decisions_md: "",
    outcome_md: "",
    stack: [],
    repo_url: "",
    map_x: null,
    map_z: null,
    published: false,
  };
}

function fromProject(p: AdminProject): Form {
  return {
    slug: p.slug,
    title: p.title,
    client: p.client ?? "",
    kind: p.kind,
    year: p.year,
    summary: p.summary,
    problem_md: p.problem_md ?? "",
    built_md: p.built_md ?? "",
    decisions_md: p.decisions_md ?? "",
    outcome_md: p.outcome_md ?? "",
    stack: [...p.stack],
    repo_url: p.repo_url ?? "",
    map_x: p.map_x,
    map_z: p.map_z,
    published: p.published,
  };
}

/** Empty optional text becomes `null`. Client projects never carry a repo URL. */
function toInput(f: Form): ProjectInput {
  const opt = (s: string): string | null => (s.trim() === "" ? null : s.trim());
  const md = (s: string): string | null => (s.trim() === "" ? null : s);
  return {
    slug: f.slug.trim(),
    title: f.title.trim(),
    client: opt(f.client),
    kind: f.kind,
    year: f.year,
    summary: f.summary.trim(),
    problem_md: md(f.problem_md),
    built_md: md(f.built_md),
    decisions_md: md(f.decisions_md),
    outcome_md: md(f.outcome_md),
    stack: f.stack.map((s) => s.trim()).filter(Boolean),
    repo_url: f.kind === "client" ? null : opt(f.repo_url),
    map_x: f.map_x,
    map_z: f.map_z,
    published: f.published,
  };
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60)
    .replace(/-+$/, "");
}

const isNew = computed(() => props.id === undefined);
const project = ref<AdminProject | null>(null);
const form = reactive<Form>(emptyForm());
const saved = ref(JSON.stringify(form));
const loading = ref(!isNew.value);
const saving = ref(false);
const loadError = ref<string | null>(null);
const saveError = ref<string | null>(null);
const slugTouched = ref(false);
const uploadingDiagram = ref(false);
const diagramInput = ref<HTMLInputElement | null>(null);

const dirty = computed(() => JSON.stringify(form) !== saved.value);
const unscrubbed = computed(() => project.value?.images.filter((i) => !i.scrubbed).length ?? 0);

watch(
  () => form.title,
  (title) => {
    if (isNew.value && !slugTouched.value) form.slug = slugify(title);
  },
);

function reset(p: AdminProject): void {
  project.value = p;
  Object.assign(form, fromProject(p));
  saved.value = JSON.stringify(form);
}

// The router reuses this view from /projects/new to /projects/:id after Create,
// so the load follows `id` instead of running once on mount.
watch(
  () => props.id,
  async (id) => {
    loadError.value = null;
    saveError.value = null;
    if (id === undefined) {
      project.value = null;
      Object.assign(form, emptyForm());
      saved.value = JSON.stringify(form);
      slugTouched.value = false;
      loading.value = false;
      return;
    }
    loading.value = true;
    try {
      reset(await api.project(id));
    } catch (err) {
      loadError.value = errorText(err);
    } finally {
      loading.value = false;
    }
  },
  { immediate: true },
);

async function save(): Promise<void> {
  saving.value = true;
  saveError.value = null;
  try {
    const input = toInput(form);
    if (props.id === undefined) {
      const created = await api.createProject(input);
      saved.value = JSON.stringify(form);
      toast.add({ severity: "success", summary: "Project created", life: 3000 });
      await router.replace({ name: "project-edit", params: { id: created.id } });
    } else {
      reset(await api.updateProject(props.id, input));
      toast.add({ severity: "success", summary: "Saved", life: 3000 });
    }
  } catch (err) {
    saveError.value = errorText(err);
  } finally {
    saving.value = false;
  }
}

function remove(): void {
  const p = project.value;
  if (!p) return;
  confirm.require({
    header: "Delete project",
    message: `Delete "${p.title}" with its ${p.images.length} images and its edges? This cannot be undone.`,
    rejectProps: { label: "Cancel", severity: "secondary", outlined: true },
    acceptProps: { label: "Delete", severity: "danger" },
    accept: async () => {
      try {
        await api.deleteProject(p.id);
        saved.value = JSON.stringify(form);
        toast.add({ severity: "success", summary: `Deleted ${p.title}`, life: 3000 });
        await router.push({ name: "projects" });
      } catch (err) {
        toast.add({ severity: "error", summary: "Delete failed", detail: errorText(err) });
      }
    },
  });
}

async function onDiagram(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || props.id === undefined) return;
  uploadingDiagram.value = true;
  try {
    const updated = await api.uploadDiagram(props.id, file);
    // Keep unsaved form edits. Only the diagram changed on the server.
    if (project.value) {
      project.value.diagram_key = updated.diagram_key;
      project.value.diagram_url = updated.diagram_url;
    }
    toast.add({ severity: "success", summary: "Diagram uploaded", life: 3000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Diagram not uploaded", detail: errorText(err) });
  } finally {
    uploadingDiagram.value = false;
  }
}

onBeforeRouteLeave(() =>
  dirty.value ? window.confirm("This project has unsaved changes. Leave anyway?") : true,
);
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div class="page-title">
        <RouterLink :to="{ name: 'projects' }" class="back">
          <i class="pi pi-arrow-left" aria-hidden="true" style="font-size: 11px" /> Projects
        </RouterLink>
        <h1>{{ isNew ? "New project" : project?.title ?? "Project" }}</h1>
      </div>
      <div class="actions">
        <span v-if="dirty" class="unsaved"><span class="dot warn" aria-hidden="true" />Unsaved changes</span>
        <Button
          v-if="!isNew && project"
          label="Delete"
          severity="danger"
          outlined
          @click="remove"
        />
        <Button
          :label="isNew ? 'Create' : 'Save'"
          icon="pi pi-check"
          :loading="saving"
          :disabled="loading || !!loadError || (!dirty && !isNew)"
          @click="save"
        />
      </div>
    </div>

    <p v-if="loadError" class="panel warn" role="alert">{{ loadError }}</p>
    <Message v-if="saveError" severity="error" :closable="false">{{ saveError }}</Message>

    <div v-if="!loading && !loadError" class="split">
      <div class="wide">
        <section class="panel" aria-label="Case study">
          <Tabs value="problem_md">
            <TabList>
              <Tab v-for="s in SECTIONS" :key="s.key" :value="s.key">{{ s.label }}</Tab>
            </TabList>
            <TabPanels style="padding: 16px 0 0">
              <TabPanel v-for="s in SECTIONS" :key="s.key" :value="s.key">
                <MarkdownField :id="`md-${s.key}`" v-model="form[s.key]" :label="s.label" :max-length="MD_MAX" />
              </TabPanel>
            </TabPanels>
          </Tabs>
        </section>

        <section v-if="project" class="panel" aria-labelledby="img-h">
          <div class="panel-head">
            <h2 id="img-h">
              <i class="pi pi-images" aria-hidden="true" /> Images
              <span class="muted" style="font-weight: 400">
                {{ project.images.length }}
                <template v-if="unscrubbed"> · {{ unscrubbed }} unscrubbed</template>
              </span>
            </h2>
            <RouterLink class="more" :to="{ name: 'images', query: { project: project.id } }">
              Manage images <i class="pi pi-arrow-right" aria-hidden="true" />
            </RouterLink>
          </div>
          <div v-if="project.images.length" class="thumbs">
            <img
              v-for="img in project.images"
              :key="img.id"
              :src="img.url"
              :alt="img.alt"
              class="thumb"
              :class="{ 'thumb-unscrubbed': !img.scrubbed }"
              loading="lazy"
            />
          </div>
          <p v-else class="muted" style="margin: 0">No images yet.</p>
        </section>
        <p v-else class="muted">Create the project first. Then you can add images and a diagram.</p>
      </div>

      <aside class="side panel" aria-label="Project details">
        <h2><i class="pi pi-sliders-h" aria-hidden="true" /> Details</h2>
        <div class="toggle-row" :class="{ on: form.published }">
          <div class="field" style="gap: 0">
            <label for="f-pub" class="field-label">Published</label>
            <span class="hint">{{ form.published ? "Goes live on the next publish" : "Draft. Stays off the site" }}</span>
          </div>
          <ToggleSwitch v-model="form.published" input-id="f-pub" />
        </div>
        <Message v-if="form.published && unscrubbed" severity="warn" :closable="false">
          Unscrubbed images on this project: {{ unscrubbed }}. Site publish stays blocked until each one is scrubbed.
        </Message>
        <span class="form-section-title">Basics</span>
        <div class="field">
          <label for="f-title">Title</label>
          <InputText id="f-title" v-model="form.title" maxlength="120" fluid />
        </div>
        <div class="field">
          <label for="f-slug">Slug</label>
          <InputText id="f-slug" v-model="form.slug" class="mono" maxlength="60" fluid @input="slugTouched = true" />
          <span class="hint">URL: /work/{{ form.slug || "…" }}. Lowercase letters, digits, and dashes.</span>
        </div>
        <div class="field">
          <span id="f-kind-label" class="field-label">Kind</span>
          <SelectButton v-model="form.kind" :options="KINDS" :allow-empty="false" aria-labelledby="f-kind-label" />
        </div>
        <div class="row-2">
          <div class="field">
            <label for="f-client">Client</label>
            <InputText id="f-client" v-model="form.client" maxlength="120" fluid />
          </div>
          <div class="field">
            <label for="f-year">Year</label>
            <InputNumber
              v-model="form.year"
              input-id="f-year"
              :use-grouping="false"
              :min="1990"
              :max="2100"
              fluid
            />
          </div>
        </div>
        <div class="field">
          <label for="f-summary">Summary</label>
          <Textarea id="f-summary" v-model="form.summary" rows="3" maxlength="300" auto-resize fluid />
          <span class="hint">Shown on the map panel. {{ form.summary.length }} / 300.</span>
        </div>
        <div class="form-section">
          <span class="form-section-title">Stack and links</span>
          <div class="field">
            <label for="f-stack">Stack</label>
            <AutoComplete v-model="form.stack" input-id="f-stack" multiple :typeahead="false" fluid />
            <span class="hint">Type a name, then press Enter. Up to 20.</span>
          </div>
          <div class="field">
            <label for="f-repo">Repo URL</label>
            <InputText
              id="f-repo"
              v-model="form.repo_url"
              type="url"
              :disabled="form.kind === 'client'"
              :placeholder="form.kind === 'client' ? 'Client projects have no repo' : 'https://github.com/…'"
              fluid
            />
          </div>
        </div>
        <div class="form-section">
          <span class="form-section-title">Diagram and map</span>
          <div class="field">
            <span class="field-label">Diagram (SVG)</span>
            <div v-if="project" class="actions" style="gap: 12px">
              <img v-if="project.diagram_url" :src="project.diagram_url" alt="Current diagram" class="thumb" style="width: 96px" />
              <span v-else class="muted">None</span>
              <input ref="diagramInput" type="file" accept="image/svg+xml,.svg" hidden @change="onDiagram" />
              <Button
                :label="project.diagram_url ? 'Replace' : 'Upload'"
                severity="secondary"
                outlined
                :loading="uploadingDiagram"
                @click="diagramInput?.click()"
              />
            </div>
            <span v-else class="hint">Available after the project is created.</span>
            <span class="hint">Uploads right away. The API strips scripts and external links.</span>
          </div>
          <div class="row-2">
            <div class="field">
              <label for="f-mx">Map X</label>
              <InputNumber v-model="form.map_x" input-id="f-mx" :min="-100" :max="100" :max-fraction-digits="2" fluid />
            </div>
            <div class="field">
              <label for="f-mz">Map Z</label>
              <InputNumber v-model="form.map_z" input-id="f-mz" :min="-100" :max="100" :max-fraction-digits="2" fluid />
            </div>
          </div>
          <span class="hint">The map editor replaces these two fields in T18.</span>
        </div>
      </aside>
    </div>
  </div>
</template>
