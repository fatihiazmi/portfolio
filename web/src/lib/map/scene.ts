/**
 * 3D systems map. Spec section 4.1 and 4.2. Runs in the browser only.
 *
 * This module owns the canvas: grid, nodes, roads, pulses, picking, and the camera.
 * `SystemsMap.astro` owns the side panel, the label text, and the node list.
 * It loads this module on demand, so three.js stays out of the first paint.
 */
import {
  BoxGeometry,
  BufferGeometry,
  Color,
  CylinderGeometry,
  EdgesGeometry,
  Float32BufferAttribute,
  Fog,
  Group,
  LineBasicMaterial,
  LineSegments,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  Raycaster,
  RingGeometry,
  Scene,
  SphereGeometry,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";

export interface MapNode {
  slug: string;
  title: string;
  kind: "client" | "personal";
  x: number;
  z: number;
}

export interface MapRoad {
  source: string;
  target: string;
}

export interface MapOptions {
  /** Positioned element the canvas fills. Its CSS sets the size. */
  host: HTMLElement;
  /** Hover label. This module shows, hides, and places it. */
  label: HTMLElement;
  nodes: MapNode[];
  roads: MapRoad[];
  /** The label now shows this node, or hides on `null`. The caller fills the label text. */
  onLabel(slug: string | null): void;
  /** A canvas click hit this node, or empty space on `null`. */
  onPick(slug: string | null): void;
  /** The first frame is on screen. */
  onReady(): void;
}

export interface MapHandle {
  /** Glow and label for a node under keyboard focus or list hover. `null` clears it. */
  highlight(slug: string | null): void;
  /**
   * Fly to a node, or back to the overview on `null`.
   * `insetRight` is the width in px that the side panel covers on the right of the canvas.
   */
  select(slug: string | null, insetRight?: number): void;
}

const FOV = 35;
const FLIGHT_MS = 800;
/** Camera distance from a selected node, in map units. */
const FOCUS_DISTANCE = 12;
/** Direction from the look-at point to the camera. About 50 degrees above the ground. */
const VIEW_DIR = new Vector3(0, 1, 0.85).normalize();
/** Map units of empty ground kept around the outermost nodes in the overview. */
const MARGIN = 1.5;
/** Extra ground beyond the far row of nodes, so their hover labels stay inside the canvas. */
const LABEL_ROOM = 2;
const GRID_HALF = 40;
const GRID_MAJOR = 5;
/** Grid drift, map units per second. */
const DRIFT = 0.15;
/** Pulse speed along a road, map units per second. */
const PULSE_SPEED = 1.6;
const PULSES_PER_ROAD = 2;
/** Camera shift at the canvas edge, map units. */
const PARALLAX = 0.5;

const SIZE = {
  client: { width: 1.4, height: 0.9, ring: 1.25 },
  personal: { width: 0.8, height: 0.5, ring: 0.8 },
} as const;

interface NodeView {
  outline: LineBasicMaterial;
  ring: Mesh<RingGeometry, MeshBasicMaterial>;
  base: Color;
  glow: number;
  /** Anchor for the hover label, just above the node. */
  top: Vector3;
  position: Vector3;
}

interface View {
  position: Vector3;
  target: Vector3;
}

/** Throws when the browser has no WebGL. The caller keeps the static SVG then. */
export function mountMap(opts: MapOptions): MapHandle {
  const { host, label } = opts;

  const css = getComputedStyle(document.documentElement);
  const token = (name: string) => new Color(css.getPropertyValue(`--color-${name}`).trim());
  const color = {
    ink950: token("ink-950"),
    ink800: token("ink-800"),
    line: token("line"),
    lineStrong: token("line-strong"),
    cyan: token("cyan"),
    paper: token("paper"),
  };

  const renderer = new WebGLRenderer({ antialias: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(color.ink950);
  const canvas = renderer.domElement;
  canvas.setAttribute("aria-hidden", "true");
  canvas.style.cssText =
    "position:absolute;inset:0;width:100%;height:100%;opacity:0;transition:opacity 400ms";
  host.append(canvas);

  const scene = new Scene();
  const camera = new PerspectiveCamera(FOV, 1, 0.1, 200);

  // Map bounds. The caller passes only nodes with a position, at least one.
  const xs = opts.nodes.map((n) => n.x);
  const zs = opts.nodes.map((n) => n.z);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minZ = Math.min(...zs);
  const maxZ = Math.max(...zs);
  const center = new Vector3((minX + maxX) / 2, 0, (minZ + maxZ - LABEL_ROOM) / 2);
  const halfX = (maxX - minX) / 2 + SIZE.client.ring + MARGIN;
  const halfZ = (maxZ - minZ + LABEL_ROOM) / 2 + SIZE.client.ring + MARGIN;

  // Ground grid, snapped to a major line near the map centre so drift wraps without a jump.
  const grid = new Group();
  const gridOrigin = new Vector3(
    Math.round(center.x / GRID_MAJOR) * GRID_MAJOR,
    0,
    Math.round(center.z / GRID_MAJOR) * GRID_MAJOR,
  );
  grid.add(
    new LineSegments(
      gridGeometry(false),
      new LineBasicMaterial({ color: color.line, transparent: true, opacity: 0.45 }),
    ),
    new LineSegments(gridGeometry(true), new LineBasicMaterial({ color: color.line })),
  );
  scene.add(grid);

  // Nodes: a block with a lit outline and a ground ring. An invisible cylinder takes the pointer.
  const views = new Map<string, NodeView>();
  const hits: Mesh[] = [];
  const hitMaterial = new MeshBasicMaterial({ visible: false });
  const bodyMaterial = new MeshBasicMaterial({ color: color.ink800 });
  for (const node of opts.nodes) {
    const size = SIZE[node.kind];
    const group = new Group();
    group.position.set(node.x, 0, node.z);

    const box = new BoxGeometry(size.width, size.height, size.width);
    const body = new Mesh(box, bodyMaterial);
    body.position.y = size.height / 2;

    const base = node.kind === "client" ? color.cyan : color.lineStrong;
    const outline = new LineBasicMaterial({ color: base.clone() });
    const edges = new LineSegments(new EdgesGeometry(box), outline);
    edges.position.y = size.height / 2;

    const ring = new Mesh(
      new RingGeometry(size.ring, size.ring + 0.06, 48),
      new MeshBasicMaterial({ color: color.cyan, transparent: true, opacity: 0.25, depthWrite: false }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.01;

    const hitHeight = size.height + 0.6;
    const hit = new Mesh(new CylinderGeometry(size.ring, size.ring, hitHeight, 16), hitMaterial);
    hit.position.y = hitHeight / 2;
    hit.userData.slug = node.slug;
    hits.push(hit);

    group.add(body, edges, ring, hit);
    scene.add(group);
    views.set(node.slug, {
      outline,
      ring,
      base,
      glow: 0,
      top: new Vector3(node.x, size.height + 0.35, node.z),
      position: new Vector3(node.x, 0, node.z),
    });
  }

  // Roads and the light pulses that travel along them.
  const roads = opts.roads.flatMap((r) => {
    const a = views.get(r.source)?.position;
    const b = views.get(r.target)?.position;
    if (!a || !b) return [];
    const from = new Vector3(a.x, 0.02, a.z);
    const to = new Vector3(b.x, 0.02, b.z);
    return [{ from, to, length: from.distanceTo(to) }];
  });
  const roadGeometry = new BufferGeometry();
  roadGeometry.setAttribute(
    "position",
    new Float32BufferAttribute(
      roads.flatMap((r) => [...r.from.toArray(), ...r.to.toArray()]),
      3,
    ),
  );
  scene.add(new LineSegments(roadGeometry, new LineBasicMaterial({ color: color.lineStrong })));

  const coreGeometry = new SphereGeometry(0.08, 12, 8);
  const haloGeometry = new SphereGeometry(0.2, 12, 8);
  const coreMaterial = new MeshBasicMaterial({ color: color.paper });
  const haloMaterial = new MeshBasicMaterial({
    color: color.cyan,
    transparent: true,
    opacity: 0.35,
    depthWrite: false,
  });
  const pulses = roads.flatMap((road) =>
    Array.from({ length: PULSES_PER_ROAD }, (_, i) => {
      const pulse = new Group();
      pulse.add(new Mesh(coreGeometry, coreMaterial), new Mesh(haloGeometry, haloMaterial));
      scene.add(pulse);
      return { road, phase: i / PULSES_PER_ROAD, object: pulse };
    }),
  );

  // Camera state. A flight eases from `from` to `to`. Parallax sits on top of the eased view.
  let overview = overviewView();
  let from: View = overview;
  let to: View = overview;
  let flightStart = -Infinity;
  const current: View = { position: overview.position.clone(), target: overview.target.clone() };
  const parallax = new Vector2();
  const parallaxGoal = new Vector2();

  let pointerSlug: string | null = null;
  let focusSlug: string | null = null;
  let selected: string | null = null;
  let inset = 0;
  let labelSlug: string | null = null;

  function overviewView(): View {
    // Fit the map box. Ground depth shows foreshortened by the camera elevation.
    const tanV = Math.tan((FOV * Math.PI) / 360);
    const tanH = tanV * camera.aspect;
    const distance = Math.max(halfX / tanH, (halfZ * VIEW_DIR.y) / tanV);
    return {
      target: center.clone(),
      position: center.clone().addScaledVector(VIEW_DIR, distance),
    };
  }

  function viewFor(slug: string | null, insetPx: number): View {
    const view = slug ? views.get(slug) : undefined;
    if (!view) return overview;
    const target = new Vector3(view.position.x, 0.3, view.position.z);
    // Shift the look-at point right so the node sits in the centre of the area the panel leaves free.
    const visibleWidth =
      2 * FOCUS_DISTANCE * Math.tan((FOV * Math.PI) / 360) * camera.aspect;
    target.x += (insetPx / 2 / Math.max(host.clientWidth, 1)) * visibleWidth;
    return { target, position: target.clone().addScaledVector(VIEW_DIR, FOCUS_DISTANCE) };
  }

  function flyTo(view: View) {
    from = { position: current.position.clone(), target: current.target.clone() };
    to = view;
    flightStart = performance.now();
  }

  function resize() {
    const width = host.clientWidth;
    const height = host.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    overview = overviewView();
    const distance = overview.position.distanceTo(overview.target);
    scene.fog = new Fog(color.ink950, distance, distance * 2.2);
    // Snap to the view for the current selection. A resize mid-flight ends the flight.
    from = to = viewFor(selected, inset);
    flightStart = -Infinity;
  }
  resize();
  new ResizeObserver(resize).observe(host);

  // Picking.
  const raycaster = new Raycaster();
  const ndc = new Vector2();
  function pick(e: MouseEvent): string | null {
    const rect = canvas.getBoundingClientRect();
    ndc.set(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    );
    raycaster.setFromCamera(ndc, camera);
    const hit = raycaster.intersectObjects(hits, false)[0];
    return (hit?.object.userData.slug as string | undefined) ?? null;
  }
  canvas.addEventListener("pointermove", (e) => {
    // Touch has no hover. A tap goes through `click`.
    if (e.pointerType === "touch") return;
    pointerSlug = pick(e);
    parallaxGoal.copy(ndc);
    canvas.style.cursor = pointerSlug ? "pointer" : "";
  });
  canvas.addEventListener("pointerleave", () => {
    pointerSlug = null;
    parallaxGoal.set(0, 0);
    canvas.style.cursor = "";
  });
  canvas.addEventListener("click", (e) => opts.onPick(pick(e)));

  // Render loop. Runs only while the canvas is on screen.
  const startedAt = performance.now();
  const anchor = new Vector3();
  let last = startedAt;
  let frameId = 0;
  let ready = false;

  function frame(now: number) {
    frameId = requestAnimationFrame(frame);
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now;
    const t = (now - startedAt) / 1000;

    const drift = (t * DRIFT) % GRID_MAJOR;
    grid.position.set(gridOrigin.x + drift, 0, gridOrigin.z + drift);

    for (const p of pulses) {
      const f = ((t * PULSE_SPEED) / p.road.length + p.phase) % 1;
      p.object.position.lerpVectors(p.road.from, p.road.to, f);
      p.object.position.y = 0.1;
    }

    const shown = pointerSlug ?? focusSlug;
    const ease = 1 - Math.exp(-dt * 10);
    for (const [slug, v] of views) {
      const goal = slug === shown || slug === selected ? 1 : 0;
      v.glow += (goal - v.glow) * ease;
      v.outline.color.lerpColors(v.base, color.paper, v.glow);
      v.ring.material.opacity = 0.25 + 0.55 * v.glow;
      v.ring.scale.setScalar(1 + 0.2 * v.glow);
    }

    const k = Math.min(Math.max((now - flightStart) / FLIGHT_MS, 0), 1);
    const e = k < 0.5 ? 4 * k * k * k : 1 - (-2 * k + 2) ** 3 / 2;
    current.position.lerpVectors(from.position, to.position, e);
    current.target.lerpVectors(from.target, to.target, e);
    parallax.lerp(parallaxGoal, 1 - Math.exp(-dt * 4));
    camera.position
      .copy(current.position)
      .add(anchor.set(parallax.x * PARALLAX, parallax.y * PARALLAX * 0.6, 0));
    camera.lookAt(current.target);

    renderer.render(scene, camera);
    placeLabel(shown && shown !== selected ? shown : null);

    if (!ready) {
      ready = true;
      canvas.style.opacity = "1";
      opts.onReady();
    }
  }

  function placeLabel(slug: string | null) {
    if (slug !== labelSlug) {
      labelSlug = slug;
      label.hidden = slug === null;
      opts.onLabel(slug);
    }
    const view = slug ? views.get(slug) : undefined;
    if (!view) return;
    anchor.copy(view.top).project(camera);
    const x = ((anchor.x + 1) / 2) * host.clientWidth;
    const y = ((1 - anchor.y) / 2) * host.clientHeight;
    label.style.transform = `translate(${x}px, ${y}px) translate(-50%, -100%)`;
  }

  new IntersectionObserver(([entry]) => {
    if (entry?.isIntersecting && !frameId) {
      last = performance.now();
      frameId = requestAnimationFrame(frame);
    } else if (!entry?.isIntersecting && frameId) {
      cancelAnimationFrame(frameId);
      frameId = 0;
    }
  }).observe(host);

  return {
    highlight(slug) {
      focusSlug = slug;
    },
    select(slug, insetRight = 0) {
      selected = slug;
      inset = insetRight;
      flyTo(viewFor(slug, insetRight));
    },
  };
}

/**
 * Grid lines one map unit apart. `major` picks every fifth line, otherwise the rest.
 * Each line is split into `GRID_MAJOR`-long segments. A single long segment that passes
 * behind the camera does not render in SwiftShader (found in a headless Chrome test).
 */
function gridGeometry(major: boolean): BufferGeometry {
  const points: number[] = [];
  for (let i = -GRID_HALF; i <= GRID_HALF; i++) {
    if ((i % GRID_MAJOR === 0) !== major) continue;
    for (let s = -GRID_HALF; s < GRID_HALF; s += GRID_MAJOR) {
      const e = s + GRID_MAJOR;
      points.push(i, 0, s, i, 0, e, s, 0, i, e, 0, i);
    }
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(points, 3));
  return geometry;
}
