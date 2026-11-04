<script setup lang="ts">
import Tag from "primevue/tag";
import { computed, onMounted, ref } from "vue";
import { api, errorText } from "../api";
import { day, when } from "../format";
import { refreshSummary, summary } from "../store";
import type { Lead } from "../types";

const leads = ref<Lead[]>([]);
const error = ref<string | null>(null);

const drafts = computed(() => (summary.value ? summary.value.projects.total - summary.value.projects.published : 0));
const publishedShare = computed(() => {
  const p = summary.value?.projects;
  return p && p.total > 0 ? Math.round((p.published / p.total) * 100) : 0;
});

onMounted(async () => {
  await refreshSummary();
  try {
    leads.value = (await api.leads({ limit: 5 })).leads;
  } catch (err) {
    error.value = errorText(err);
  }
});
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div class="page-title">
        <h1>Dashboard</h1>
        <p class="page-sub">New leads, content state, and what blocks the next publish.</p>
      </div>
    </div>
    <p v-if="error" class="panel warn" role="alert">{{ error }}</p>

    <section v-if="summary" class="cards" aria-label="Summary">
      <div class="panel stat-card">
        <div class="stat-top">
          <span class="stat-label">New leads</span>
          <span class="stat-icon" aria-hidden="true"><i class="pi pi-inbox" /></span>
        </div>
        <span class="stat">{{ summary.leads.new }}</span>
        <div class="stat-foot">
          <span>of {{ summary.leads.total }} total</span>
          <RouterLink class="more" :to="{ name: 'leads', query: { status: 'new' } }">
            Open <i class="pi pi-arrow-right" aria-hidden="true" />
          </RouterLink>
        </div>
      </div>

      <div class="panel stat-card">
        <div class="stat-top">
          <span class="stat-label">Projects published</span>
          <span class="stat-icon" aria-hidden="true"><i class="pi pi-folder" /></span>
        </div>
        <span class="stat">{{ summary.projects.published }}<small> / {{ summary.projects.total }}</small></span>
        <div class="meter" aria-hidden="true">
          <span :style="{ width: `${publishedShare}%` }" />
        </div>
        <div class="stat-foot">
          <span>{{ drafts }} draft{{ drafts === 1 ? "" : "s" }}</span>
          <RouterLink class="more" :to="{ name: 'projects' }">
            Open <i class="pi pi-arrow-right" aria-hidden="true" />
          </RouterLink>
        </div>
      </div>

      <div class="panel stat-card" :class="{ warn: summary.blocking_images > 0 }">
        <div class="stat-top">
          <span class="stat-label">Blocking images</span>
          <span class="stat-icon" :class="summary.blocking_images > 0 ? 'warn' : 'ok'" aria-hidden="true">
            <i :class="summary.blocking_images > 0 ? 'pi pi-exclamation-triangle' : 'pi pi-check'" />
          </span>
        </div>
        <span class="stat">{{ summary.blocking_images }}</span>
        <div class="stat-foot">
          <template v-if="summary.blocking_images > 0">
            <span>Unscrubbed on published projects</span>
            <RouterLink class="more" :to="{ name: 'images' }" style="color: var(--warn-text)">
              Review <i class="pi pi-arrow-right" aria-hidden="true" />
            </RouterLink>
          </template>
          <span v-else>Nothing blocks publish</span>
        </div>
      </div>

      <div class="panel stat-card">
        <div class="stat-top">
          <span class="stat-label">Last backup</span>
          <span class="stat-icon calm" aria-hidden="true"><i class="pi pi-database" /></span>
        </div>
        <span class="stat" :class="{ muted: !summary.last_backup_at }">
          {{ summary.last_backup_at ? day(summary.last_backup_at) : "—" }}
        </span>
        <div class="stat-foot">
          <span v-if="summary.last_backup_at">{{ when(summary.last_backup_at) }}</span>
          <span v-else>No data until T20 wires Litestream metrics</span>
        </div>
      </div>
    </section>

    <div class="split">
      <section class="wide panel flush" aria-labelledby="leads-h">
        <div class="panel-head" style="padding: 18px 24px">
          <h2 id="leads-h"><i class="pi pi-inbox" aria-hidden="true" /> Newest leads</h2>
          <RouterLink class="more" :to="{ name: 'leads' }">
            All leads <i class="pi pi-arrow-right" aria-hidden="true" />
          </RouterLink>
        </div>
        <div v-if="leads.length === 0" class="empty-state">
          <i class="pi pi-inbox" aria-hidden="true" />
          <strong>No leads yet</strong>
          <span>Contact form messages show here.</span>
        </div>
        <div v-else style="overflow-x: auto">
          <table class="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Kind</th>
                <th>Received</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="lead in leads" :key="lead.id">
                <td>
                  <div class="who">
                    <span class="avatar" aria-hidden="true">{{ lead.name.charAt(0) }}</span>
                    <RouterLink :to="{ name: 'leads', query: { lead: lead.id } }">{{ lead.name }}</RouterLink>
                  </div>
                </td>
                <td><span class="chip">{{ lead.kind }}</span></td>
                <td class="muted" style="white-space: nowrap">{{ day(lead.created_at) }}</td>
                <td>
                  <Tag :value="lead.status" :severity="lead.status === 'new' ? 'info' : 'secondary'" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="summary" class="side panel" aria-labelledby="pub-h">
        <h2 id="pub-h"><i class="pi pi-cloud-upload" aria-hidden="true" /> Publish</h2>
        <dl class="facts">
          <div>
            <dt>Last publish</dt>
            <dd>{{ summary.last_publish ? when(summary.last_publish.created_at) : "Never" }}</dd>
          </div>
          <div v-if="summary.last_publish">
            <dt>Deploy ID</dt>
            <dd class="mono">{{ summary.last_publish.deploy_id ?? "not returned" }}</dd>
          </div>
          <div>
            <dt>Live projects</dt>
            <dd>{{ summary.projects.published }}</dd>
          </div>
          <div>
            <dt>Blocking images</dt>
            <dd :style="summary.blocking_images > 0 ? 'color: var(--warn-text); font-weight: 600' : ''">
              {{ summary.blocking_images }}
            </dd>
          </div>
        </dl>
        <p class="hint" style="margin: 0">
          Publish starts a Cloudflare Pages build from the published projects. Drafts stay out.
        </p>
      </section>
    </div>
  </div>
</template>
