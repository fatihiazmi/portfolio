<script setup lang="ts">
import Button from "primevue/button";
import ConfirmDialog from "primevue/confirmdialog";
import Toast from "primevue/toast";
import { computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import PublishButton from "./components/PublishButton.vue";
import { when } from "./format";
import { adminEmail, loadMe, refreshSummary, summary } from "./store";

const route = useRoute();

const CRUMBS: Record<string, string[]> = {
  dashboard: ["dashboard"],
  projects: ["projects"],
  "project-new": ["projects", "new"],
  "project-edit": ["projects", "edit"],
  map: ["map"],
  images: ["images"],
  leads: ["leads"],
};
const crumbs = computed(() => CRUMBS[String(route.name)] ?? []);

// One line on the publish state, next to the Publish button.
const publishState = computed(() => {
  const s = summary.value;
  if (!s) return null;
  if (s.blocking_images > 0) {
    const n = s.blocking_images;
    return { tone: "warn", text: `${n} image${n === 1 ? "" : "s"} block publish` };
  }
  if (s.last_publish) return { tone: "ok", text: `Published ${when(s.last_publish.created_at)}` };
  return { tone: "", text: "Not published yet" };
});

onMounted(() => {
  void loadMe();
  void refreshSummary();
});
// Keeps the nav badge current as the owner moves between screens.
watch(
  () => route.name,
  () => void refreshSummary(),
);
</script>

<template>
  <div class="shell">
    <nav class="nav" aria-label="Admin sections">
      <RouterLink class="brand" :to="{ name: 'dashboard' }">
        <span class="brand-mark" aria-hidden="true">FA</span>
        <span class="brand-text">
          <span class="brand-name">fatihiazmi.dev</span>
          <span class="brand-sub">Admin</span>
        </span>
      </RouterLink>

      <div class="nav-groups">
        <div class="nav-group">
          <span class="nav-label">Overview</span>
          <RouterLink
            class="nav-link"
            :to="{ name: 'dashboard' }"
            active-class=""
            exact-active-class="router-link-active"
          >
            <i class="pi pi-th-large" aria-hidden="true" /> Dashboard
          </RouterLink>
        </div>
        <div class="nav-group">
          <span class="nav-label">Content</span>
          <RouterLink class="nav-link" :to="{ name: 'projects' }">
            <i class="pi pi-folder" aria-hidden="true" /> Projects
          </RouterLink>
          <RouterLink class="nav-link" :to="{ name: 'images' }">
            <i class="pi pi-images" aria-hidden="true" /> Images
          </RouterLink>
          <RouterLink class="nav-link" :to="{ name: 'map' }">
            <i class="pi pi-map" aria-hidden="true" /> Map editor
          </RouterLink>
        </div>
        <div class="nav-group">
          <span class="nav-label">Inbox</span>
          <RouterLink class="nav-link" :to="{ name: 'leads' }">
            <i class="pi pi-inbox" aria-hidden="true" /> Leads
            <span v-if="summary?.leads.new" class="nav-count">
              {{ summary.leads.new }}<span class="sr-only"> new</span>
            </span>
          </RouterLink>
        </div>
      </div>

      <div v-if="adminEmail" class="nav-foot">
        <span class="avatar" aria-hidden="true">{{ adminEmail.charAt(0) }}</span>
        <span class="nav-foot-text">
          <strong :title="adminEmail">{{ adminEmail }}</strong>
          <span>Cloudflare Access</span>
        </span>
      </div>
    </nav>

    <div class="main">
      <header class="topbar">
        <div class="crumbs" aria-hidden="true">
          <span>admin</span>
          <template v-for="(c, i) in crumbs" :key="c">
            <span>/</span>
            <strong v-if="i === crumbs.length - 1">{{ c }}</strong>
            <span v-else>{{ c }}</span>
          </template>
        </div>
        <div class="topbar-right">
          <span v-if="publishState" class="status-pill">
            <span class="dot" :class="publishState.tone" aria-hidden="true" />
            {{ publishState.text }}
          </span>
          <Button
            as="a"
            href="https://fatihiazmi.dev"
            target="_blank"
            rel="noopener"
            label="View site"
            icon="pi pi-external-link"
            icon-pos="right"
            severity="secondary"
            text
          />
          <PublishButton />
        </div>
      </header>
      <main>
        <RouterView />
      </main>
    </div>
  </div>
  <Toast position="bottom-right" />
  <ConfirmDialog />
</template>
