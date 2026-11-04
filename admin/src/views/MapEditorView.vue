<script setup lang="ts">
// Map editor. Spec section 9.2, plan T18.
// Top-down view of the 3D systems map: x to the right, z down, the same as the site's static map.
// Drag a node to set map_x and map_z. Click two nodes to add or remove a road (an edge).
// Nothing saves until Save map. Then one PATCH per moved project and one PUT for the roads.
import Button from "primevue/button";
import InputText from "primevue/inputtext";
import Tag from "primevue/tag";
import ToggleSwitch from "primevue/toggleswitch";
import { useToast } from "primevue/usetoast";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { onBeforeRouteLeave, useRoute } from "vue-router";
import { api, errorText } from "../api";
import { refreshSummary } from "../store";
import type { AdminEdge, AdminProject, ProjectKind } from "../types";

interface Point {
  x: number;
  z: number;
}

interface View {
  x: number;
  z: number;
  w: number;
  h: number;
}

type Drag =
  | { kind: "node"; id: number; startX: number; startY: number; offset: Point; moved: boolean }
  | { kind: "pan"; startX: number; startY: number; from: View; moved: boolean };

/** Ring radius of each node kind on the 3D map, in map units. Keep in step with `web/src/lib/map/scene.ts`. */
const RING: Record<ProjectKind, number> = { client: 1.25, personal: 0.8 };
const CORE: Record<ProjectKind, number> = { client: 0.42, personal: 0.28 };
/** The API accepts -100 to 100 on both axes. */
const LIMIT = 100;
/** Canvas width to height. The SVG has the same aspect ratio, so one map unit is square. */
const ASPECT = 1.6;
const MIN_W = 12;
const MAX_W = 200;
/** Pointer travel in px before a press counts as a drag, not a click. */
const DRAG_PX = 4;

const route = useRoute();
const toast = useToast();

const projects = ref<AdminProject[]>([]);
const pos = ref<Record<number, Point | null>>({});
const savedPos = ref<Record<number, Point | null>>({});
const edges = ref<AdminEdge[]>([]);
const savedEdges = ref<AdminEdge[]>([]);
const selected = ref<number | null>(null);
const snap = ref(true);
const view = ref<View>({ x: -12, z: -7.5, w: 24, h: 15 });
const cursor = ref<Point | null>(null);
const dragging = ref<number | null>(null);
const panning = ref(false);
const status = ref("");
const loading = ref(true);
const saving = ref(false);
const error = ref<string | null>(null);
const svg = ref<SVGSVGElement | null>(null);
/** Rendered canvas width in px. Labels use it to keep one size on screen at any zoom. */
const canvasPx = ref(800);
let drag: Drag | null = null;
let fitted = false;
let resize: ResizeObserver | null = null;

// --- Derived state ---

const byId = computed(() => new Map(projects.value.map((p) => [p.id, p])));
const placed = computed(() =>
  projects.value.flatMap((p) => {
    const at = pos.value[p.id];
    return at ? [{ p, at }] : [];
  }),
);
const unplaced = computed(() => projects.value.filter((p) => !pos.value[p.id]));
const current = computed(() => (selected.value === null ? null : (byId.value.get(selected.value) ?? null)));

function samePoint(a: Point | null | undefined, b: Point | null | undefined): boolean {
  if (!a || !b) return !a && !b;
  return a.x === b.x && a.z === b.z;
}

/** Roads without direction and with trimmed labels, in a stable order. Used to spot changes. */
function edgeKey(list: AdminEdge[]): string {
  const norm = list.map((e) => ({
    a: Math.min(e.from_id, e.to_id),
    b: Math.max(e.from_id, e.to_id),
    label: e.label?.trim() || null,
  }));
  norm.sort((m, n) => m.a - n.a || m.b - n.b);
  return JSON.stringify(norm);
}

const movedProjects = computed(() => projects.value.filter((p) => !samePoint(pos.value[p.id], savedPos.value[p.id])));
const edgesChanged = computed(() => edgeKey(edges.value) !== edgeKey(savedEdges.value));
const dirty = computed(() => movedProjects.value.length > 0 || edgesChanged.value);

const roads = computed(() =>
  edges.value.flatMap((e) => {
    const a = pos.value[e.from_id];
    const b = pos.value[e.to_id];
    return a && b ? [{ key: `${e.from_id}-${e.to_id}`, a, b }] : [];
  }),
);
const roadRows = computed(() =>
  edges.value.map((e, index) => ({
    e,
    index,
    from: byId.value.get(e.from_id)?.title ?? `#${e.from_id}`,
    to: byId.value.get(e.to_id)?.title ?? `#${e.to_id}`,
    hidden: !pos.value[e.from_id] || !pos.value[e.to_id],
    draft: !byId.value.get(e.from_id)?.published || !byId.value.get(e.to_id)?.published,
  })),
);

/** Node pairs whose rings touch. The 3D map would draw them on top of each other. */
const overlaps = computed(() => {
  const list = placed.value;
  const out: { a: AdminProject; b: AdminProject }[] = [];
  for (const [i, m] of list.entries()) {
    for (const n of list.slice(i + 1)) {
      const gap = Math.hypot(m.at.x - n.at.x, m.at.z - n.at.z);
      if (gap < RING[m.p.kind] + RING[n.p.kind]) out.push({ a: m.p, b: n.p });
    }
  }
  return out;
});
const clashing = computed(() => new Set(overlaps.value.flatMap((o) => [o.a.id, o.b.id])));

function roadCount(id: number): number {
  return edges.value.filter((e) => e.from_id === id || e.to_id === id).length;
}

/** Label size in map units: 12.5 px on screen, 10.5 px on a phone, at any zoom. */
const font = computed(() => ((canvasPx.value < 500 ? 10.5 : 12.5) * view.value.w) / canvasPx.value);

const grid = computed(() => {
  const { x, z, w, h } = view.value;
  const step = w > 90 ? 5 : 1;
  let minor = "";
  let major = "";
  for (let gx = Math.ceil(x / step) * step; gx <= x + w; gx += step) {
    const line = `M${gx} ${z}V${z + h}`;
    if (gx % 5 === 0) major += line;
    else minor += line;
  }
  for (let gz = Math.ceil(z / step) * step; gz <= z + h; gz += step) {
    const line = `M${x} ${gz}H${x + w}`;
    if (gz % 5 === 0) major += line;
    else minor += line;
  }
  return { minor, major };
});

/** Dashed line from the picked node to the pointer while a road waits for its second end. */
const pending = computed(() => {
  const from = selected.value === null ? null : pos.value[selected.value];
  return from && cursor.value && dragging.value === null ? { a: from, b: cursor.value } : null;
});

const readout = computed(() => {
  if (dragging.value !== null) {
    const at = pos.value[dragging.value];
    const name = byId.value.get(dragging.value)?.title ?? "";
    return at ? `${name} · x ${fmt(at.x)}, z ${fmt(at.z)}` : "";
  }
  return cursor.value ? `x ${fmt(cursor.value.x)}, z ${fmt(cursor.value.z)}` : "";
});

function fmt(v: number): string {
  return (Math.round(v * 10) / 10).toFixed(1);
}

function nodeLabel(p: AdminProject, at: Point): string {
  const state = p.published ? "" : ", draft";
  return `${p.title}, ${p.kind}${state}, at x ${fmt(at.x)}, z ${fmt(at.z)}, ${roadCount(p.id)} roads`;
}

// --- Load, save, discard ---

function positions(list: AdminProject[]): Record<number, Point | null> {
  return Object.fromEntries(
    list.map((p) => [p.id, p.map_x !== null && p.map_z !== null ? { x: p.map_x, z: p.map_z } : null]),
  );
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = null;
  try {
    const res = await api.projects();
    projects.value = res.projects;
    pos.value = positions(res.projects);
    savedPos.value = positions(res.projects);
    edges.value = res.edges.map((e) => ({ ...e }));
    savedEdges.value = res.edges.map((e) => ({ ...e }));
    const wanted = Number(route.query.project);
    if (!fitted) {
      selected.value = pos.value[wanted] ? wanted : null;
      fit();
      fitted = true;
    }
  } catch (err) {
    error.value = errorText(err);
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  saving.value = true;
  const failures: string[] = [];
  for (const p of [...movedProjects.value]) {
    const at = pos.value[p.id] ?? null;
    try {
      await api.moveProject(p.id, { map_x: at?.x ?? null, map_z: at?.z ?? null });
    } catch (err) {
      failures.push(`${p.title}: ${errorText(err)}`);
    }
  }
  if (edgesChanged.value) {
    try {
      await api.saveEdges(edges.value.map((e) => ({ ...e, label: e.label?.trim() || null })));
    } catch (err) {
      failures.push(`Roads: ${errorText(err)}`);
    }
  }
  saving.value = false;
  if (failures.length === 0) {
    toast.add({
      severity: "success",
      summary: "Map saved",
      detail: "Publish the site to update the live map.",
      life: 4000,
    });
    await load();
  } else {
    toast.add({ severity: "error", summary: "Some changes were not saved", detail: failures.join("\n") });
  }
  void refreshSummary();
}

function discard(): void {
  pos.value = { ...savedPos.value };
  edges.value = savedEdges.value.map((e) => ({ ...e }));
  selected.value = null;
  status.value = "Changes discarded.";
}

// --- View ---

function fit(): void {
  const pts = placed.value.map((n) => n.at);
  if (pts.length === 0) {
    view.value = { x: -12, z: -7.5, w: 24, h: 15 };
    return;
  }
  const xs = pts.map((p) => p.x);
  const zs = pts.map((p) => p.z);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minZ = Math.min(...zs);
  const maxZ = Math.max(...zs);
  // Room for rings and the labels under the bottom row.
  let w = Math.max(maxX - minX + 8, MIN_W * 2);
  let h = Math.max(maxZ - minZ + 9, (MIN_W * 2) / ASPECT);
  if (w / h > ASPECT) h = w / ASPECT;
  else w = h * ASPECT;
  view.value = { x: (minX + maxX) / 2 - w / 2, z: (minZ + maxZ + 1) / 2 - h / 2, w, h };
}

function zoom(factor: number): void {
  const v = view.value;
  const w = Math.min(MAX_W, Math.max(MIN_W, v.w * factor));
  const h = w / ASPECT;
  view.value = { x: v.x + (v.w - w) / 2, z: v.z + (v.h - h) / 2, w, h };
}

// --- Editing ---

function clamp(v: number): number {
  return Math.max(-LIMIT, Math.min(LIMIT, v));
}

/** Snap to whole map units, or to 0.1 with snap off. `|| 0` turns -0 into 0. */
function snapPoint(p: Point): Point {
  const step = snap.value ? 1 : 0.1;
  const r = (v: number) => Math.round(clamp(Math.round(v / step) * step) * 100) / 100 || 0;
  return { x: r(p.x), z: r(p.z) };
}

function title(id: number): string {
  return byId.value.get(id)?.title ?? `#${id}`;
}

function toggleRoad(a: number, b: number): void {
  const i = edges.value.findIndex(
    (e) => (e.from_id === a && e.to_id === b) || (e.from_id === b && e.to_id === a),
  );
  if (i >= 0) {
    edges.value.splice(i, 1);
    status.value = `Road removed: ${title(a)} to ${title(b)}.`;
  } else {
    edges.value.push({ from_id: a, to_id: b, label: null });
    status.value = `Road added: ${title(a)} to ${title(b)}.`;
  }
}

/** First click picks a node. A click on a second node toggles the road between them. */
function pick(id: number): void {
  const first = selected.value;
  if (first === id) {
    selected.value = null;
    status.value = "";
  } else if (first === null) {
    selected.value = id;
    status.value = `${title(id)} picked. Click another node to add or remove a road.`;
  } else {
    toggleRoad(first, id);
    selected.value = null;
  }
}

function place(id: number): void {
  const v = view.value;
  const c = { x: Math.round(v.x + v.w / 2), z: Math.round(v.z + v.h / 2) };
  const taken = (p: Point) => placed.value.some((n) => Math.hypot(n.at.x - p.x, n.at.z - p.z) < 2.5);
  const candidates: Point[] = [c];
  for (let r = 3; r <= 24; r += 3) {
    for (const [dx, dz] of [
      [r, 0],
      [0, r],
      [-r, 0],
      [0, -r],
    ] as const) {
      candidates.push({ x: c.x + dx, z: c.z + dz });
    }
  }
  pos.value[id] = snapPoint(candidates.find((p) => !taken(p)) ?? c);
  selected.value = null;
  status.value = `${title(id)} placed. Drag it where it belongs.`;
}

function unplace(id: number): void {
  pos.value[id] = null;
  selected.value = null;
  status.value = `${title(id)} taken off the map. Its roads stay saved but hidden.`;
}

function removeRoad(index: number): void {
  const e = edges.value[index];
  if (!e) return;
  edges.value.splice(index, 1);
  status.value = `Road removed: ${title(e.from_id)} to ${title(e.to_id)}.`;
}

// --- Pointer and keyboard ---

function toMap(e: PointerEvent): Point | null {
  const m = svg.value?.getScreenCTM();
  if (!m) return null;
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
  return { x: p.x, z: p.y };
}

function onNodeDown(e: PointerEvent, id: number): void {
  const at = pos.value[id];
  const m = toMap(e);
  if (e.button !== 0 || !at || !m) return;
  e.stopPropagation();
  svg.value?.setPointerCapture(e.pointerId);
  drag = { kind: "node", id, startX: e.clientX, startY: e.clientY, offset: { x: at.x - m.x, z: at.z - m.z }, moved: false };
}

function onCanvasDown(e: PointerEvent): void {
  if (e.button !== 0) return;
  svg.value?.setPointerCapture(e.pointerId);
  drag = { kind: "pan", startX: e.clientX, startY: e.clientY, from: { ...view.value }, moved: false };
}

function onMove(e: PointerEvent): void {
  const m = toMap(e);
  if (!drag) {
    cursor.value = m;
    return;
  }
  if (!drag.moved && Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < DRAG_PX) return;
  drag.moved = true;
  if (drag.kind === "node") {
    dragging.value = drag.id;
    if (m) pos.value[drag.id] = snapPoint({ x: m.x + drag.offset.x, z: m.z + drag.offset.z });
  } else {
    panning.value = true;
    const perPx = drag.from.w / Math.max(svg.value?.clientWidth ?? 1, 1);
    view.value = {
      ...drag.from,
      x: drag.from.x - (e.clientX - drag.startX) * perPx,
      z: drag.from.z - (e.clientY - drag.startY) * perPx,
    };
  }
}

function onUp(): void {
  if (drag && !drag.moved) {
    if (drag.kind === "node") pick(drag.id);
    else if (selected.value !== null) {
      selected.value = null;
      status.value = "";
    }
  }
  drag = null;
  dragging.value = null;
  panning.value = false;
}

function onNodeKey(e: KeyboardEvent, id: number): void {
  const at = pos.value[id];
  if (!at) return;
  const step = e.shiftKey ? 5 : 1;
  const moves: Record<string, Point> = {
    ArrowLeft: { x: -step, z: 0 },
    ArrowRight: { x: step, z: 0 },
    ArrowUp: { x: 0, z: -step },
    ArrowDown: { x: 0, z: step },
  };
  const move = moves[e.key];
  if (move) {
    e.preventDefault();
    pos.value[id] = snapPoint({ x: at.x + move.x, z: at.z + move.z });
  } else if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    pick(id);
  } else if (e.key === "Escape" && selected.value !== null) {
    selected.value = null;
    status.value = "";
  }
}

onBeforeRouteLeave(() =>
  dirty.value ? window.confirm("The map changes are not saved. Leave anyway?") : true,
);
onMounted(() => {
  void load();
  if (svg.value) {
    resize = new ResizeObserver(([entry]) => {
      if (entry) canvasPx.value = Math.max(entry.contentRect.width, 1);
    });
    resize.observe(svg.value);
  }
});
onBeforeUnmount(() => resize?.disconnect());
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div class="page-title">
        <h1>Map editor</h1>
        <p class="page-sub">
          Top-down view of the 3D systems map. Drag a node to move it. Click two nodes to add or remove a road.
        </p>
      </div>
      <div class="actions">
        <span v-if="dirty" class="unsaved"><span class="dot warn" aria-hidden="true" />Unsaved changes</span>
        <Button v-if="dirty" label="Discard" severity="secondary" outlined @click="discard" />
        <Button label="Save map" icon="pi pi-check" :loading="saving" :disabled="!dirty" @click="save" />
      </div>
    </div>
    <p v-if="error" class="panel warn" role="alert">{{ error }}</p>

    <div class="split">
      <section class="wide panel flush" aria-label="Map">
        <div class="map-wrap">
          <svg
            ref="svg"
            class="map-canvas"
            :class="{ panning }"
            :viewBox="`${view.x} ${view.z} ${view.w} ${view.h}`"
            role="group"
            aria-label="Systems map, top-down. Tab to a node, arrow keys move it, Enter picks it for a road."
            @pointerdown="onCanvasDown"
            @pointermove="onMove"
            @pointerup="onUp"
            @pointercancel="onUp"
            @pointerleave="cursor = null"
          >
            <path :d="grid.minor" class="g-minor" />
            <path :d="grid.major" class="g-major" />
            <path d="M-0.5 0H0.5M0 -0.5V0.5" class="g-origin" />
            <line
              v-for="r in roads"
              :key="r.key"
              :x1="r.a.x"
              :y1="r.a.z"
              :x2="r.b.x"
              :y2="r.b.z"
              class="road"
            />
            <line
              v-if="pending"
              :x1="pending.a.x"
              :y1="pending.a.z"
              :x2="pending.b.x"
              :y2="pending.b.z"
              class="road pending"
            />
            <g
              v-for="n in placed"
              :key="n.p.id"
              class="node"
              :class="[n.p.kind, { draft: !n.p.published, sel: selected === n.p.id, drag: dragging === n.p.id, clash: clashing.has(n.p.id) }]"
              :transform="`translate(${n.at.x} ${n.at.z})`"
              :data-id="n.p.id"
              tabindex="0"
              role="button"
              :aria-label="nodeLabel(n.p, n.at)"
              :aria-pressed="selected === n.p.id"
              @pointerdown="onNodeDown($event, n.p.id)"
              @keydown="onNodeKey($event, n.p.id)"
            >
              <circle :r="RING[n.p.kind]" class="ring" />
              <circle :r="CORE[n.p.kind]" class="core" />
              <text :y="RING[n.p.kind] + font * 1.25" :font-size="font" text-anchor="middle">{{ n.p.title }}</text>
            </g>
          </svg>

          <div class="map-tools">
            <button type="button" class="tool" aria-label="Zoom in" title="Zoom in" @click="zoom(0.8)">
              <i class="pi pi-plus" aria-hidden="true" />
            </button>
            <button type="button" class="tool" aria-label="Zoom out" title="Zoom out" @click="zoom(1.25)">
              <i class="pi pi-minus" aria-hidden="true" />
            </button>
            <button type="button" class="tool" aria-label="Fit all nodes" title="Fit all nodes" @click="fit">
              <i class="pi pi-expand" aria-hidden="true" />
            </button>
          </div>
          <div v-if="readout" class="map-readout" aria-hidden="true">{{ readout }}</div>
          <div v-if="!loading && projects.length === 0" class="map-empty">
            No projects yet. <RouterLink :to="{ name: 'project-new' }">Create one</RouterLink> first.
          </div>
        </div>

        <div class="map-foot">
          <div class="legend" aria-hidden="true">
            <span><i class="lg-dot client" />Client</span>
            <span><i class="lg-dot personal" />Personal</span>
            <span><i class="lg-dot draft" />Draft</span>
            <span><i class="lg-road" />Road</span>
          </div>
          <label class="snap">
            <ToggleSwitch v-model="snap" input-id="m-snap" />
            Snap to whole units
          </label>
        </div>
        <p class="map-status" aria-live="polite">{{ status }}</p>
      </section>

      <aside class="side map-side">
        <section v-if="overlaps.length" class="panel warn" role="status" aria-labelledby="clash-h">
          <h2 id="clash-h" style="color: inherit">
            <i class="pi pi-exclamation-triangle" aria-hidden="true" style="color: inherit" /> Nodes overlap
          </h2>
          <ul class="howto" style="color: inherit">
            <li v-for="o in overlaps" :key="`${o.a.id}-${o.b.id}`">{{ o.a.title }} and {{ o.b.title }}</li>
          </ul>
          <p style="margin: 0">The live map draws them on top of each other. Drag one away.</p>
        </section>
        <section class="panel" aria-labelledby="sel-h">
          <template v-if="current">
            <h2 id="sel-h"><i class="pi pi-map-marker" aria-hidden="true" /> {{ current.title }}</h2>
            <div class="actions" style="gap: 8px">
              <span class="chip">{{ current.kind }}</span>
              <Tag
                :value="current.published ? 'published' : 'draft'"
                :severity="current.published ? 'success' : 'secondary'"
              />
            </div>
            <dl class="facts">
              <div>
                <dt>map_x</dt>
                <dd class="mono">{{ pos[current.id]?.x ?? "—" }}</dd>
              </div>
              <div>
                <dt>map_z</dt>
                <dd class="mono">{{ pos[current.id]?.z ?? "—" }}</dd>
              </div>
              <div>
                <dt>Roads</dt>
                <dd>{{ roadCount(current.id) }}</dd>
              </div>
            </dl>
            <p class="hint" style="margin: 0">
              Click another node to add or remove a road to it. Click empty ground or press Escape to cancel.
            </p>
            <div class="panel-head">
              <RouterLink class="more" :to="{ name: 'project-edit', params: { id: current.id } }">
                Edit project <i class="pi pi-arrow-right" aria-hidden="true" />
              </RouterLink>
              <Button label="Take off the map" severity="danger" text size="small" @click="unplace(current.id)" />
            </div>
          </template>
          <template v-else>
            <h2 id="sel-h"><i class="pi pi-info-circle" aria-hidden="true" /> How it works</h2>
            <ul class="howto">
              <li>Drag a node to move it. With snap on, it lands on whole map units.</li>
              <li>Click a node, then another, to add a road. Do it again to remove the road.</li>
              <li>Drag empty ground to pan. The buttons on the map zoom and fit.</li>
              <li>Tab to a node. Arrow keys move it, Shift moves 5. Enter picks it for a road.</li>
            </ul>
          </template>
        </section>

        <section v-if="unplaced.length" class="panel" aria-labelledby="off-h">
          <h2 id="off-h">
            <i class="pi pi-eye-slash" aria-hidden="true" /> Not on the map
            <span class="muted" style="font-weight: 400">{{ unplaced.length }}</span>
          </h2>
          <p class="hint" style="margin: 0">The live map leaves these projects out.</p>
          <ul class="plain-list">
            <li v-for="p in unplaced" :key="p.id">
              <span class="row-name">{{ p.title }}</span>
              <Button label="Place" icon="pi pi-plus" size="small" outlined @click="place(p.id)" />
            </li>
          </ul>
        </section>

        <section class="panel" aria-labelledby="roads-h">
          <h2 id="roads-h">
            <i class="pi pi-share-alt" aria-hidden="true" /> Roads
            <span class="muted" style="font-weight: 400">{{ edges.length }}</span>
          </h2>
          <p v-if="edges.length === 0" class="hint" style="margin: 0">No roads yet. Click two nodes to join them.</p>
          <ul v-else class="plain-list">
            <li v-for="row in roadRows" :key="`${row.e.from_id}-${row.e.to_id}`" class="road-row">
              <div class="road-head">
                <span class="row-name">{{ row.from }} <span class="muted">↔</span> {{ row.to }}</span>
                <Button
                  icon="pi pi-times"
                  text
                  rounded
                  severity="secondary"
                  size="small"
                  :aria-label="`Remove road ${row.from} to ${row.to}`"
                  @click="removeRoad(row.index)"
                />
              </div>
              <InputText
                :model-value="row.e.label ?? ''"
                size="small"
                maxlength="80"
                placeholder="Label, such as payroll"
                :aria-label="`Label for road ${row.from} to ${row.to}`"
                fluid
                @update:model-value="(v) => (row.e.label = v || null)"
              />
              <span v-if="row.hidden" class="hint">Hidden: one end is not on the map.</span>
              <span v-else-if="row.draft" class="hint">Off the live map until both ends are published.</span>
            </li>
          </ul>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.map-wrap {
  position: relative;
  background: var(--ink-950);
}

.map-canvas {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 10;
  touch-action: none;
  user-select: none;
  cursor: grab;
}

.map-canvas.panning {
  cursor: grabbing;
}

.g-minor,
.g-major,
.g-origin,
.road,
.node circle {
  vector-effect: non-scaling-stroke;
}

.g-minor {
  fill: none;
  stroke: rgb(28 66 112 / 55%);
  stroke-width: 1;
}

.g-major {
  fill: none;
  stroke: var(--ink-line);
  stroke-width: 1.5;
}

.g-origin {
  stroke: #3b7bc0;
  stroke-width: 1.5;
}

.road {
  stroke: #3b7bc0;
  stroke-width: 2;
  stroke-dasharray: 6 5;
}

.road.pending {
  stroke: var(--amber);
  pointer-events: none;
}

.node {
  cursor: move;
  outline: none;
}

.node .ring {
  fill: rgb(92 200 255 / 8%);
  stroke: rgb(92 200 255 / 35%);
  stroke-width: 1;
}

.node .core {
  fill: var(--ink-900);
  stroke: var(--cyan);
  stroke-width: 2;
}

.node.client .core {
  fill: var(--cyan);
}

.node text {
  fill: var(--paper-muted);
  font-family: var(--mono);
  pointer-events: none;
}

.node.client text {
  fill: var(--paper);
}

.node.draft {
  opacity: 0.55;
}

.node.draft .ring {
  stroke-dasharray: 3 3;
}

.node:hover .ring {
  fill: rgb(92 200 255 / 16%);
  stroke: var(--cyan);
}

.node:focus-visible .ring,
.node.sel .ring {
  fill: rgb(255 181 71 / 14%);
  stroke: var(--amber);
  stroke-width: 2;
}

.node.clash .ring {
  fill: rgb(248 113 113 / 16%);
  stroke: #f87171;
  stroke-width: 2;
}

.node.drag .ring {
  fill: rgb(92 200 255 / 22%);
  stroke: var(--cyan);
  stroke-width: 2;
}

.map-tools {
  position: absolute;
  top: 12px;
  right: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tool {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--ink-line);
  border-radius: 8px;
  background: rgb(10 28 48 / 90%);
  color: var(--paper);
  cursor: pointer;
}

.tool:hover {
  border-color: #3b7bc0;
  color: var(--cyan);
}

.tool:focus-visible {
  outline: 2px solid var(--amber);
  outline-offset: 2px;
}

.map-readout {
  position: absolute;
  left: 12px;
  bottom: 12px;
  padding: 4px 10px;
  border: 1px solid var(--ink-line);
  border-radius: 6px;
  background: rgb(10 28 48 / 90%);
  color: var(--paper-muted);
  font: 12px var(--mono);
  pointer-events: none;
}

.map-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--paper-muted);
}

.map-empty a {
  color: var(--cyan);
}

.map-foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 20px;
  padding: 12px 16px;
  border-top: 1px solid var(--line);
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font: 12px var(--mono);
  color: var(--muted);
}

.legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.lg-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  box-sizing: border-box;
  border: 2px solid #2c64a3;
}

.lg-dot.client {
  background: #2c64a3;
}

.lg-dot.draft {
  border-style: dashed;
  opacity: 0.6;
}

.lg-road {
  width: 18px;
  border-top: 2px dashed #3b7bc0;
}

.snap {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.map-status {
  margin: 0;
  padding: 0 16px 12px;
  min-height: 1.5em;
  color: var(--muted);
  font-size: 13px;
}

.map-status:empty {
  padding: 0;
  min-height: 0;
}

.map-side {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.howto {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  color: var(--muted);
}

.plain-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.plain-list > li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--line-soft);
}

.plain-list > li:first-child {
  border-top: 0;
  padding-top: 0;
}

.plain-list > li.road-row {
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
}

.road-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.row-name {
  font-weight: 500;
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
