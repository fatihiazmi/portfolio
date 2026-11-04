<script setup lang="ts">
// Project list. Drag rows to change the order, then Save order sends the full id list.
import Button from "primevue/button";
import Column from "primevue/column";
import DataTable, { type DataTableRowReorderEvent } from "primevue/datatable";
import Tag from "primevue/tag";
import { useToast } from "primevue/usetoast";
import { computed, onMounted, ref } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { api, errorText } from "../api";
import { day } from "../format";
import type { AdminProject } from "../types";

const toast = useToast();
const rows = ref<AdminProject[]>([]);
const savedIds = ref<number[]>([]);
const loading = ref(true);
const saving = ref(false);
const error = ref<string | null>(null);

const orderChanged = computed(() => rows.value.some((p, i) => p.id !== savedIds.value[i]));

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    rows.value = (await api.projects()).projects;
    savedIds.value = rows.value.map((p) => p.id);
  } catch (err) {
    error.value = errorText(err);
  } finally {
    loading.value = false;
  }
}

function onReorder(event: DataTableRowReorderEvent): void {
  rows.value = event.value as AdminProject[];
}

function discard(): void {
  const byId = new Map(rows.value.map((p) => [p.id, p]));
  rows.value = savedIds.value.map((id) => byId.get(id)).filter((p): p is AdminProject => !!p);
}

async function saveOrder(): Promise<void> {
  saving.value = true;
  try {
    const ids = rows.value.map((p) => p.id);
    await api.saveOrder(ids);
    savedIds.value = ids;
    toast.add({ severity: "success", summary: "Order saved", life: 3000 });
  } catch (err) {
    toast.add({ severity: "error", summary: "Order not saved", detail: errorText(err) });
  } finally {
    saving.value = false;
  }
}

function unscrubbed(p: AdminProject): number {
  return p.images.filter((i) => !i.scrubbed).length;
}

onBeforeRouteLeave(() =>
  orderChanged.value ? window.confirm("The new order is not saved. Leave anyway?") : true,
);
onMounted(load);
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div class="page-title">
        <h1>Projects</h1>
        <p class="page-sub">Drag a row by its handle to change the list and map order. Save order applies it.</p>
      </div>
      <div class="actions">
        <template v-if="orderChanged">
          <Button label="Discard order" severity="secondary" outlined @click="discard" />
          <Button label="Save order" icon="pi pi-check" :loading="saving" @click="saveOrder" />
        </template>
        <RouterLink v-slot="{ navigate }" :to="{ name: 'project-new' }" custom>
          <Button label="New project" icon="pi pi-plus" :outlined="orderChanged" @click="navigate" />
        </RouterLink>
      </div>
    </div>
    <p v-if="error" class="panel warn" role="alert">{{ error }}</p>

    <div class="panel flush">
      <DataTable :value="rows" :loading="loading" data-key="id" @row-reorder="onReorder">
        <template #empty><div class="empty">No projects yet.</div></template>
        <Column row-reorder header-style="width: 3rem" />
        <Column header="Title">
          <template #body="{ data }">
            <div class="title-cell">
              <RouterLink :to="{ name: 'project-edit', params: { id: data.id } }">{{ data.title }}</RouterLink>
              <div class="mono muted">/work/{{ data.slug }}</div>
            </div>
          </template>
        </Column>
        <Column header="Kind">
          <template #body="{ data }"><span class="chip">{{ data.kind }}</span></template>
        </Column>
        <Column header="Year">
          <template #body="{ data }">{{ data.year ?? "—" }}</template>
        </Column>
        <Column header="Status">
          <template #body="{ data }">
            <Tag
              :value="data.published ? 'published' : 'draft'"
              :severity="data.published ? 'success' : 'secondary'"
            />
          </template>
        </Column>
        <Column header="Images">
          <template #body="{ data }">
            <div class="actions" style="gap: 6px">
              <span class="chip"><i class="pi pi-image" aria-hidden="true" />{{ data.images.length }}</span>
              <RouterLink
                v-if="unscrubbed(data)"
                class="chip warn"
                :to="{ name: 'images', query: { project: data.id } }"
              >
                {{ unscrubbed(data) }} unscrubbed
              </RouterLink>
            </div>
          </template>
        </Column>
        <Column header="Updated">
          <template #body="{ data }"><span class="muted">{{ day(data.updated_at) }}</span></template>
        </Column>
      </DataTable>
    </div>
    <p class="hint" style="margin: 0">
      Drafts never block publish. Only images on published projects must be scrubbed.
    </p>
  </div>
</template>
