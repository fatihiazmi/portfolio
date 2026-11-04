<script setup lang="ts">
// Starts a Pages build. A 409 means images on published projects are not scrubbed:
// the dialog lists them, each with a link to its project's images.
import Button from "primevue/button";
import Dialog from "primevue/dialog";
import { useConfirm } from "primevue/useconfirm";
import { useToast } from "primevue/usetoast";
import { ref } from "vue";
import { api, blockedImageIds, errorText } from "../api";
import { refreshSummary } from "../store";

interface BlockedImage {
  id: number;
  url: string;
  alt: string;
  projectId: number;
  projectTitle: string;
}

const confirm = useConfirm();
const toast = useToast();
const busy = ref(false);
const blocked = ref<BlockedImage[] | null>(null);

function ask(): void {
  confirm.require({
    header: "Publish site",
    message: "Start a Cloudflare Pages build with the published projects?",
    rejectProps: { label: "Cancel", severity: "secondary", outlined: true },
    acceptProps: { label: "Publish" },
    accept: run,
  });
}

async function run(): Promise<void> {
  busy.value = true;
  try {
    const record = await api.publish();
    toast.add({
      severity: "success",
      summary: "Pages build started",
      detail: record.deploy_id ? `Deploy ${record.deploy_id}` : undefined,
      life: 6000,
    });
  } catch (err) {
    const ids = blockedImageIds(err);
    if (ids) {
      blocked.value = await describe(ids);
    } else {
      toast.add({ severity: "error", summary: "Publish failed", detail: errorText(err) });
    }
  } finally {
    busy.value = false;
    void refreshSummary();
  }
}

async function describe(ids: number[]): Promise<BlockedImage[]> {
  const wanted = new Set(ids);
  try {
    const { projects } = await api.projects();
    return projects.flatMap((p) =>
      p.images
        .filter((i) => wanted.has(i.id))
        .map((i) => ({
          id: i.id,
          url: i.url,
          alt: i.alt,
          projectId: p.id,
          projectTitle: p.title,
        })),
    );
  } catch {
    return ids.map((id) => ({ id, url: "", alt: `Image ${id}`, projectId: 0, projectTitle: "" }));
  }
}
</script>

<template>
  <Button label="Publish site" icon="pi pi-cloud-upload" :loading="busy" @click="ask" />
  <Dialog
    :visible="blocked !== null"
    modal
    header="Publish blocked"
    :style="{ width: 'min(560px, calc(100vw - 32px))' }"
    @update:visible="blocked = null"
  >
    <p style="margin-top: 0">
      These images belong to published projects and are not marked scrubbed. Check each one for
      personal data first.
    </p>
    <ul style="list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px">
      <li
        v-for="img in blocked ?? []"
        :key="img.id"
        style="display: flex; align-items: center; gap: 12px"
      >
        <img v-if="img.url" :src="img.url" :alt="img.alt" class="thumb" style="width: 64px" />
        <span style="flex: 1; min-width: 0">{{ img.projectTitle }} · {{ img.alt }}</span>
        <RouterLink
          v-if="img.projectId"
          :to="{ name: 'images', query: { project: img.projectId } }"
          @click="blocked = null"
        >
          Review
        </RouterLink>
      </li>
    </ul>
  </Dialog>
</template>
