<script setup lang="ts">
// Contact form leads. Filter by kind and status. A status change saves at once.
import Button from "primevue/button";
import Column from "primevue/column";
import DataTable from "primevue/datatable";
import Select from "primevue/select";
import SelectButton from "primevue/selectbutton";
import Tag from "primevue/tag";
import { useToast } from "primevue/usetoast";
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { api, errorText } from "../api";
import { day, when } from "../format";
import { refreshSummary } from "../store";
import type { Lead, LeadKind, LeadStatus } from "../types";

const KINDS: LeadKind[] = ["freelance", "hiring", "other"];
const STATUSES: LeadStatus[] = ["new", "replied", "closed"];

const route = useRoute();
const router = useRouter();
const toast = useToast();

function pick<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.includes(value as T) ? (value as T) : null;
}

const kind = ref<LeadKind | null>(pick(route.query.kind, KINDS));
const status = ref<LeadStatus | null>(pick(route.query.status, STATUSES));
const leads = ref<Lead[]>([]);
const total = ref(0);
const selected = ref<Lead | null>(null);
const loading = ref(true);
const updating = ref(false);
const error = ref<string | null>(null);

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const res = await api.leads({ kind: kind.value, status: status.value });
    leads.value = res.leads;
    total.value = res.total;
    const wanted = selected.value?.id ?? Number(route.query.lead);
    selected.value = leads.value.find((l) => l.id === wanted) ?? leads.value[0] ?? null;
  } catch (err) {
    error.value = errorText(err);
  } finally {
    loading.value = false;
  }
}

watch([kind, status], () => {
  const query: Record<string, string> = {};
  if (kind.value) query.kind = kind.value;
  if (status.value) query.status = status.value;
  void router.replace({ query });
  void load();
});

async function setStatus(next: LeadStatus | null): Promise<void> {
  const lead = selected.value;
  if (!lead || !next || next === lead.status) return;
  updating.value = true;
  try {
    const updated = await api.setLeadStatus(lead.id, next);
    leads.value = leads.value.map((l) => (l.id === updated.id ? updated : l));
    selected.value = updated;
    void refreshSummary();
  } catch (err) {
    toast.add({ severity: "error", summary: "Status not saved", detail: errorText(err) });
  } finally {
    updating.value = false;
  }
}

// A click on the selected row would clear the selection and hide the detail. Keep it.
function onSelect(lead: Lead | null): void {
  if (lead) selected.value = lead;
}

function severity(s: LeadStatus): string {
  return s === "new" ? "info" : s === "replied" ? "secondary" : "contrast";
}

onMounted(load);
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div class="page-title">
        <h1>Leads</h1>
        <p class="page-sub">Contact form messages. WhatsApp leads skip the database and do not show here.</p>
      </div>
    </div>
    <p v-if="error" class="panel warn" role="alert">{{ error }}</p>

    <div class="panel" style="flex-direction: row; flex-wrap: wrap; align-items: flex-end">
      <div class="field" style="width: 180px">
        <label for="l-kind">Kind</label>
        <Select v-model="kind" :options="KINDS" input-id="l-kind" placeholder="All kinds" show-clear fluid />
      </div>
      <div class="field" style="width: 180px">
        <label for="l-status">Status</label>
        <Select v-model="status" :options="STATUSES" input-id="l-status" placeholder="All statuses" show-clear fluid />
      </div>
      <span class="muted" style="min-height: 40px; display: flex; align-items: center; margin-left: auto">
        {{ total }} leads<template v-if="total > leads.length">, newest {{ leads.length }} shown</template>
      </span>
    </div>

    <div class="split">
      <div class="wide panel flush">
        <DataTable
          :selection="selected"
          :value="leads"
          data-key="id"
          selection-mode="single"
          :meta-key-selection="false"
          :loading="loading"
          scrollable
          @update:selection="onSelect"
        >
          <template #empty><div class="empty">No leads match these filters.</div></template>
          <Column header="Received">
            <template #body="{ data }"><span style="white-space: nowrap">{{ day(data.created_at) }}</span></template>
          </Column>
          <Column header="Name">
          <template #body="{ data }">
            <div class="who">
              <span class="avatar" aria-hidden="true">{{ data.name.charAt(0) }}</span>
              <span style="font-weight: 500">{{ data.name }}</span>
            </div>
          </template>
        </Column>
          <Column header="Company">
            <template #body="{ data }">{{ data.company ?? "—" }}</template>
          </Column>
          <Column header="Kind">
          <template #body="{ data }"><span class="chip">{{ data.kind }}</span></template>
        </Column>
          <Column header="Status">
            <template #body="{ data }"><Tag :value="data.status" :severity="severity(data.status)" /></template>
          </Column>
        </DataTable>
      </div>

      <section v-if="selected" class="side panel" aria-labelledby="lead-h">
        <div class="who" style="gap: 12px">
          <span class="avatar" style="width: 44px; height: 44px; font-size: 17px" aria-hidden="true">
            {{ selected.name.charAt(0) }}
          </span>
          <div class="field" style="gap: 0">
            <h2 id="lead-h">{{ selected.name }}</h2>
            <span class="hint">{{ when(selected.created_at) }}</span>
          </div>
        </div>
        <div class="row-2">
          <div class="field">
            <span class="hint">Email</span>
            <a :href="`mailto:${selected.email}`" style="overflow-wrap: anywhere">{{ selected.email }}</a>
          </div>
          <div class="field">
            <span class="hint">Company</span>
            <span>{{ selected.company ?? "—" }}</span>
          </div>
          <div class="field">
            <span class="hint">Kind</span>
            <span>{{ selected.kind }}</span>
          </div>
          <div class="field">
            <span class="hint">Budget</span>
            <span>{{ selected.budget ?? "—" }}</span>
          </div>
        </div>
        <div class="field">
          <span class="hint">Message</span>
          <p class="message-box">{{ selected.message }}</p>
        </div>
        <Button
          as="a"
          :href="`mailto:${selected.email}`"
          label="Reply by email"
          icon="pi pi-envelope"
          outlined
        />
        <div class="field">
          <span id="lead-status" class="hint">Status</span>
          <SelectButton
            :model-value="selected.status"
            :options="STATUSES"
            :allow-empty="false"
            :disabled="updating"
            aria-labelledby="lead-status"
            @update:model-value="setStatus"
          />
        </div>
      </section>
    </div>
  </div>
</template>
