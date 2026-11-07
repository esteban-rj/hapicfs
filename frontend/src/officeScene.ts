// Inspired by hermes-game-studio/hermes-office-3d's local Three.js diorama.
// Hapic supplies its own project roster, activity and conversation navigation.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";
import type { Agent, Project } from "./api";
import { officeColors, officeLayout, officePresence, type OfficeExecution } from "./officeModel";

export type OfficeScene = {
  update: (members: Agent[], execution?: OfficeExecution) => void;
  select: (id: string) => void;
  view: (overhead: boolean) => void;
  zoom: (factor: number) => void;
  dispose: () => void;
};
type Actor = { root: THREE.Group; arms: THREE.Group[]; ring: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>; working: boolean; light: THREE.MeshStandardMaterial };

export function createProjectOfficeScene(host: HTMLElement, project: Project, members: Agent[], onSelect: (id: string) => void, onError: (message: string) => void): OfficeScene {
  const layout = officeLayout(members.length);
  const { width, depth } = layout;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#192b30");
  const geometries = new Map<string, THREE.BufferGeometry>();
  const materials = new Map<string, THREE.MeshStandardMaterial>();
  const textures = new Set<THREE.Texture>();
  const extraMaterials = new Set<THREE.Material>();
  const cleanups: (() => void)[] = [];
  const interactive: THREE.Object3D[] = [];
  const actors = new Map<string, Actor>();
  const labels = new Map<string, HTMLButtonElement>();
  const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
  let disposed = false;
  let contextLost = false;
  let frame = 0;
  let lastFrame = 0;
  let selected = "";
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "low-power" });
  const cleanup = () => {
    if (disposed) return;
    disposed = true;
    cancelAnimationFrame(frame);
    cleanups.forEach(fn => fn());
    geometries.forEach(g => g.dispose());
    materials.forEach(m => m.dispose());
    extraMaterials.forEach(m => m.dispose());
    textures.forEach(t => t.dispose());
    labels.forEach(label => label.remove());
    renderer.dispose();
    renderer.forceContextLoss();
    renderer.domElement.remove();
  };
  try {
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    renderer.domElement.setAttribute("aria-label", "Oficina 3D de " + project.name + ". Arrastra para girar y usa los controles para acercar. El equipo también está disponible en la lista.");
    renderer.domElement.setAttribute("role", "img");
    host.append(renderer.domElement);
    const camera = new THREE.OrthographicCamera(-10, 10, 8, -8, .1, 250);
    const controls = new OrbitControls(camera, renderer.domElement);
    cleanups.push(() => controls.dispose());
    controls.enableDamping = !reducedMotion.matches;
    controls.dampingFactor = .09;
    controls.minZoom = .55;
    controls.maxZoom = 3;
    controls.minPolarAngle = .05;
    controls.maxPolarAngle = Math.PI / 2.2;
    controls.maxTargetRadius = Math.max(width, depth);
    const ambient = new THREE.HemisphereLight("#e0efeb", "#a17c5c", 2.4);
    scene.add(ambient);
    const sun = new THREE.DirectionalLight("#ffe5c2", 3.2);
    sun.position.set(-3, 16, 10);
    sun.castShadow = true;
    sun.shadow.mapSize.set(1024, 1024);
    Object.assign(sun.shadow.camera, { left: -width, right: width, top: depth, bottom: -depth, far: 70 });
    sun.shadow.bias = -.0005;
    sun.shadow.normalBias = .04;
    scene.add(sun);
    const rim = new THREE.DirectionalLight("#adcce8", 1.2);
    rim.position.set(8, 6, -6);
    scene.add(rim);

    function mat(color: string, extra: THREE.MeshStandardMaterialParameters = {}) {
      const key = color + JSON.stringify(extra);
      if (!materials.has(key)) materials.set(key, new THREE.MeshStandardMaterial({ color, roughness: .78, ...extra }));
      return materials.get(key)!;
    }
    function geometry(key: string, create: () => THREE.BufferGeometry) {
      if (!geometries.has(key)) geometries.set(key, create());
      return geometries.get(key)!;
    }
    function box(parent: THREE.Object3D, size: [number, number, number], pos: [number, number, number], color: string, radius = .025, extra?: THREE.MeshStandardMaterialParameters) {
      const geo = geometry("box:" + size.join() + ":" + radius, () => radius ? new RoundedBoxGeometry(...size, 2, Math.min(radius, Math.min(...size) / 2)) : new THREE.BoxGeometry(...size));
      const mesh = new THREE.Mesh(geo, mat(color, extra));
      mesh.position.set(...pos);
      mesh.castShadow = mesh.receiveShadow = true;
      parent.add(mesh);
      return mesh;
    }
    function cylinder(parent: THREE.Object3D, top: number, bottom: number, height: number, pos: [number, number, number], color: string) {
      const geo = geometry(`cyl:${top},${bottom},${height}`, () => new THREE.CylinderGeometry(top, bottom, height, 12));
      const mesh = new THREE.Mesh(geo, mat(color));
      mesh.position.set(...pos);
      mesh.castShadow = mesh.receiveShadow = true;
      parent.add(mesh);
      return mesh;
    }
    function sphere(parent: THREE.Object3D, size: [number, number, number], pos: [number, number, number], color: string) {
      const mesh = new THREE.Mesh(geometry("sphere", () => new THREE.SphereGeometry(1, 12, 8)), mat(color));
      mesh.scale.set(...size);
      mesh.position.set(...pos);
      mesh.castShadow = true;
      parent.add(mesh);
      return mesh;
    }
    function group(parent: THREE.Object3D, pos: [number, number, number]) {
      const g = new THREE.Group(); g.position.set(...pos); parent.add(g); return g;
    }
    function surface(parent: THREE.Object3D, size: [number, number], pos: [number, number, number], paint: (ctx: CanvasRenderingContext2D) => void, transparent = false) {
      const canvas = document.createElement("canvas");
      canvas.width = 768; canvas.height = 384;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas unavailable");
      paint(ctx);
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      textures.add(texture);
      const material = new THREE.MeshBasicMaterial({ map: texture, transparent, toneMapped: false });
      extraMaterials.add(material);
      const mesh = new THREE.Mesh(geometry("plane:" + size.join(), () => new THREE.PlaneGeometry(...size)), material);
      mesh.position.set(...pos); parent.add(mesh); return mesh;
    }
    function plant(parent: THREE.Object3D, x: number, z: number, scale = 1) {
      const pot = group(parent, [x, 0, z]); pot.scale.setScalar(scale);
      cylinder(pot, .23, .17, .37, [0, .2, 0], "#c08f70");
      cylinder(pot, .2, .2, .025, [0, .4, 0], "#4d4234");
      cylinder(pot, .025, .035, .8, [0, .8, 0], "#597d57");
      for (let i = 0; i < 7; i++) {
        const a = i * 2.4;
        const leaf = sphere(pot, [.16, .36, .07], [Math.sin(a) * .23, .66 + i * .09, Math.cos(a) * .23], i % 2 ? "#8aa276" : "#496f58");
        leaf.rotation.set(Math.cos(a) * .55, a, Math.sin(a) * .55);
      }
    }

    // Open walls and locally modeled furniture; no remote assets or demo agents.
    box(scene, [width + .35, .4, depth + .35], [0, -.25, 0], "#45605b", .12);
    box(scene, [width, .1, depth], [0, -.015, 0], "#b6936f");
    const planks = Math.ceil(depth / .38);
    for (let row = 0; row < planks; row++) {
      const z = -depth / 2 + (row + .5) * depth / planks;
      for (let col = 0; col < 6; col++) {
        box(scene, [width / 6 - .015, .012, depth / planks - .013], [-width / 2 + (col + .5) * width / 6, .045, z], ["#b89674", "#c1a17f", "#b38f6c", "#c6a681"][(row + col * 3) % 4], 0);
      }
    }
    box(scene, [width + .2, 3, .15], [0, 1.46, -depth / 2], "#35574f");
    box(scene, [.15, 3, depth], [-width / 2, 1.46, 0], "#436158");
    box(scene, [width + .25, .12, .23], [0, 3, -depth / 2], "#bba179");
    box(scene, [.23, .12, depth], [-width / 2, 3, 0], "#bba179");
    box(scene, [width, .12, .08], [0, .13, -depth / 2 + .1], "#bea783");
    box(scene, [.08, .12, depth], [-width / 2 + .1, .13, 0], "#bea783");
    const officeWidth = layout.columns * 2.8;
    for (let i = 0; i < layout.columns; i++) {
      const x = -width / 2 + 1.8 + i * 2.8;
      box(scene, [2.15, 1.35, .08], [x, 1.9, -depth / 2 + .1], "#213e40");
      box(scene, [1.99, 1.2, .025], [x, 1.9, -depth / 2 + .15], "#9cbcb7", .015, { emissive: "#9cbcb7", emissiveIntensity: .15 });
      for (let b = 0; b < 6; b++) {
        const h = .18 + ((b * 7 + i * 3) % 5) * .12;
        box(scene, [.27, h, .03], [x - .83 + b * .33, 1.32 + h / 2, -depth / 2 + .18], b % 2 ? "#6b9290" : "#7c9c92", 0);
      }
      box(scene, [.055, 1.25, .07], [x, 1.9, -depth / 2 + .22], "#e0d6b9", 0);
      box(scene, [2.3, .08, .26], [x, 1.24, -depth / 2 + .21], "#ccaf85");
    }
    surface(scene, [officeWidth - .4, .35], [-width / 2 + officeWidth / 2 + .4, 2.76, -depth / 2 + .12], ctx => {
      ctx.fillStyle = "#e9dfc4"; ctx.font = "500 230px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText("H A P I C   /   P R O J E C T   S T U D I O", 384, 192, 730);
    }, true);

    function makeDesk(agent: Agent, index: number) {
      const { x, z } = layout.seats[index];
      const tint = officeColors[agent.kind];
      const d = group(scene, [x, 0, z]);
      box(d, [2.34, .018, 2.48], [0, .061, .26], "#7d8c7b", .04);
      box(d, [1.95, .12, .87], [0, .89, -.22], "#d3b38b", .065);
      for (const dx of [-.8, .8]) for (const dz of [-.53, .08]) box(d, [.07, .82, .07], [dx, .44, dz], "#39504b", .01);
      box(d, [.55, .025, .21], [0, .97, -.36], "#39504b");
      box(d, [.06, .27, .06], [0, 1.09, -.41], "#39504b");
      box(d, [1.12, .68, .07], [0, 1.43, -.42], "#253f41", .04);
      surface(d, [1.01, .57], [0, 1.43, -.38], ctx => {
        ctx.fillStyle = "#1e343c"; ctx.fillRect(0, 0, 768, 384);
        ctx.fillStyle = "#385057"; ctx.fillRect(0, 0, 768, 35);
        ["#d69386", "#d6ba7d", "#94b69a"].forEach((c, i) => { ctx.fillStyle = c; ctx.beginPath(); ctx.arc(22 + i * 25, 17, 6, 0, Math.PI * 2); ctx.fill(); });
        if (agent.kind === "graphic-designer" || agent.kind === "ux") {
          ctx.fillStyle = "#dfd5bb"; ctx.fillRect(60, 65, 645, 275);
          ctx.fillStyle = tint; ctx.fillRect(94, 97, 230, 210);
          ctx.fillStyle = "#709a8c"; ctx.beginPath(); ctx.arc(490, 200, 97, 0, Math.PI * 2); ctx.fill();
        } else {
          for (let i = 0; i < 10; i++) { ctx.fillStyle = i % 3 ? "#9db6b1" : tint; ctx.fillRect(45 + (i % 3) * 18, 70 + i * 27, 120 + (i * 73) % 430, 8); }
        }
      });
      box(d, [.68, .03, .2], [0, .968, .08], "#a9b6a4", .015);
      sphere(d, [.065, .024, .085], [.49, .974, .08], "#d7d9c5");
      cylinder(d, .075, .065, .17, [-.73, 1.015, .03], "#e4d7bc");
      cylinder(d, .06, .06, .006, [-.73, 1.104, .03], "#5c4033");
      box(d, [.25, .035, .3], [.73, .976, -.31], tint);
      cylinder(d, .035, .035, .44, [0, .32, .69], "#344d48");
      box(d, [.58, .13, .54], [0, .56, .69], tint, .07);
      box(d, [.6, .55, .12], [0, .84, .94], tint, .07);
      const light = new THREE.MeshStandardMaterial({ color: tint, emissive: tint, emissiveIntensity: .1 });
      extraMaterials.add(light);
      const lightMesh = new THREE.Mesh(geometry("status", () => new THREE.SphereGeometry(.05, 8, 6)), light);
      lightMesh.position.set(.52, 1.75, -.38); d.add(lightMesh);
      d.userData.agentId = agent.id; interactive.push(d);

      const root = group(scene, [x + .5, .06, z + .92]);
      const skin = ["#d6ab87", "#aa795c", "#e4bc9a", "#bc8968"][index % 4];
      const hair = ["#443b36", "#3d3438", "#805d46", "#343c3a"][index % 4];
      for (const dx of [-.105, .105]) {
        box(root, [.16, .38, .2], [dx, .3, 0], "#43545d", .04);
        box(root, [.18, .105, .28], [dx, .1, .04], "#2b3d40", .03);
      }
      box(root, [.46, .43, .28], [0, .67, 0], tint, .07);
      cylinder(root, .075, .075, .11, [0, .91, 0], skin);
      box(root, [.38, .38, .35], [0, 1.12, 0], skin, .09);
      box(root, [.41, .15, .38], [0, 1.3, -.02], hair, .06);
      box(root, [.4, .22, .12], [0, 1.18, -.16], hair, .04);
      for (const dx of [-.085, .085]) sphere(root, [.024, .031, .017], [dx, 1.13, .175], "#2b3737");
      box(root, [.06, .012, .012], [0, 1.02, .178], "#975f4e", .003);
      const arms: THREE.Group[] = [];
      for (const dx of [-.3, .3]) {
        const arm = group(root, [dx, .82, 0]);
        box(arm, [.16, .29, .19], [0, -.12, 0], tint, .04);
        sphere(arm, [.075, .085, .075], [0, -.3, 0], skin); arms.push(arm);
      }
      if (agent.kind === "coder") {
        for (const dx of [-.22, .22]) box(root, [.075, .15, .12], [dx, 1.17, 0], "#395970", .02);
        box(root, [.45, .05, .17], [0, 1.34, -.015], "#395970");
      }
      if (agent.kind === "architect" || agent.kind === "hapic") {
        for (const dx of [-.087, .087]) box(root, [.13, .09, .015], [dx, 1.13, .19], "#526561", .009, { transparent: true, opacity: .7 });
      }
      const ringGeometry = geometry("ring", () => new THREE.RingGeometry(.36, .4, 40)) as THREE.RingGeometry;
      const ringMaterial = new THREE.MeshBasicMaterial({ color: tint, transparent: true, opacity: .45, side: THREE.DoubleSide });
      extraMaterials.add(ringMaterial);
      const ring = new THREE.Mesh(ringGeometry, ringMaterial); ring.rotation.x = -Math.PI / 2; ring.position.y = .025; root.add(ring);
      root.userData.agentId = agent.id; interactive.push(root);
      actors.set(agent.id, { root, arms, ring, working: false, light });
      const label = document.createElement("button");
      label.type = "button"; label.className = "office-world-label"; label.textContent = agent.name;
      label.setAttribute("aria-label", "Seleccionar a " + agent.name);
      label.addEventListener("click", () => select(agent.id));
      host.append(label); labels.set(agent.id, label);
    }
    members.forEach(makeDesk);

    // A shared lounge and project board finish each project's own space.
    const loungeX = width / 2 - 2.2;
    box(scene, [3.45, .025, Math.min(5, depth - 1.6)], [loungeX, .07, .45], "#7c887a", .07);
    box(scene, [2.8, .38, .68], [loungeX, .33, -depth / 2 + .7], "#9f8465", .05);
    const board = group(scene, [loungeX, 1.85, -depth / 2 + .14]);
    box(board, [3.2, 1.65, .08], [0, 0, 0], "#263e40", .04);
    surface(board, [3, 1.45], [0, 0, .05], ctx => {
      ctx.fillStyle = "#e2dac3"; ctx.fillRect(0, 0, 768, 384);
      ctx.fillStyle = "#527163"; ctx.font = "500 22px sans-serif"; ctx.fillText("EL PRÓXIMO PASO EMPIEZA AQUÍ", 42, 55);
      ctx.fillStyle = "#263f3c"; ctx.font = "600 44px sans-serif";
      const title = project.name.length > 30 ? project.name.slice(0, 29) + "…" : project.name;
      ctx.fillText(title, 42, 129, 682);
      ["#d8b780", "#9ab7a1", "#bcabc7"].forEach((c, i) => {
        ctx.fillStyle = c; ctx.fillRect(42 + i * 232, 180, 211, 120);
        ctx.fillStyle = "#496257"; ctx.fillRect(59 + i * 232, 201, 100, 6); ctx.fillRect(59 + i * 232, 224, 163, 4); ctx.fillRect(59 + i * 232, 241, 124, 4);
      });
      ctx.fillStyle = "#65776b"; ctx.font = "20px sans-serif"; ctx.fillText(`${members.length} AGENTES  /  UN MISMO PROYECTO`, 42, 350);
    });
    const sofa = group(scene, [loungeX + .1, 0, depth / 2 - 1.3]);
    box(sofa, [2.6, .36, .87], [0, .42, 0], "#be9c76", .12);
    box(sofa, [2.65, .57, .23], [0, .74, .35], "#c6aa85", .09);
    for (const x of [-1.25, 1.25]) box(sofa, [.22, .5, .95], [x, .6, 0], "#c6aa85", .07);
    for (const x of [-.75, 0, .75]) box(sofa, [.69, .11, .63], [x, .65, -.1], "#d1b791", .07);
    box(sofa, [.45, .4, .14], [-.7, .95, .16], "#668c79", .07).rotation.z = -.2;
    cylinder(scene, .7, .7, .09, [loungeX, .5, depth / 2 - 2.7], "#d5b790");
    for (const dx of [-.4, .4]) cylinder(scene, .04, .05, .43, [loungeX + dx, .24, depth / 2 - 2.7], "#455b51");
    box(scene, [.4, .04, .3], [loungeX, .575, depth / 2 - 2.7], "#80987d");
    plant(scene, width / 2 - .62, -depth / 2 + .65, 1.2);
    plant(scene, -width / 2 + .6, depth / 2 - .6, 1.2);
    plant(scene, width / 2 - .65, depth / 2 - .5, .9);
    box(scene, [.055, 1.15, depth - 1], [loungeX - 1.95, .68, -.1], "#c4ded0", .005, { transparent: true, opacity: .14, depthWrite: false });
    for (const z of [-depth / 2 + .4, depth / 2 - .6]) box(scene, [.055, 1.6, .06], [loungeX - 1.95, .83, z], "#6c8c7e", .01);

    function view(overhead: boolean) {
      controls.target.set(0, .65, 0);
      camera.position.set(overhead ? .01 : width * .95, Math.max(width, depth) * (overhead ? 1.8 : 1.15), overhead ? .01 : depth * 1.65);
      camera.zoom = 1; camera.updateProjectionMatrix(); controls.update();
    }
    function resize() {
      const w = host.clientWidth, h = host.clientHeight;
      if (!w || !h || disposed) return;
      const aspect = w / h;
      const half = Math.max(depth * .79, width * .47, (width + depth) * .52 / aspect);
      camera.left = -half * aspect; camera.right = half * aspect; camera.top = half; camera.bottom = -half;
      camera.updateProjectionMatrix(); renderer.setSize(w, h);
    }
    const observer = new ResizeObserver(resize); observer.observe(host);
    cleanups.push(() => observer.disconnect());
    resize(); view(false);
    function select(id: string) {
      selected = id;
      labels.forEach((label, key) => { label.classList.toggle("selected", key === id); label.setAttribute("aria-pressed", String(key === id)); });
      onSelect(id);
    }
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let down: { x: number; y: number; id: number } | undefined;
    const pointers = new Set<number>();
    let multiplePointers = false;
    function pointerDown(event: PointerEvent) {
      pointers.add(event.pointerId);
      if (pointers.size > 1) multiplePointers = true;
      if (event.button === 0) down = { x: event.clientX, y: event.clientY, id: event.pointerId };
    }
    function pointerUp(event: PointerEvent) {
      pointers.delete(event.pointerId);
      if (multiplePointers) { down = undefined; if (!pointers.size) multiplePointers = false; return; }
      if (!down || down.id !== event.pointerId || Math.hypot(event.clientX - down.x, event.clientY - down.y) > 5) { down = undefined; return; }
      down = undefined;
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(interactive, true)[0];
      let object: THREE.Object3D | null = hit?.object || null;
      while (object && !object.userData.agentId) object = object.parent;
      if (object) select(object.userData.agentId);
    }
    function cancelPointer(event: PointerEvent) { pointers.delete(event.pointerId); down = undefined; if (!pointers.size) multiplePointers = false; }
    function contextError(event: Event) { event.preventDefault(); contextLost = true; cancelAnimationFrame(frame); onError("Se interrumpió el renderizado. Pulsa Reintentar para reconstruir la oficina."); }
    renderer.domElement.addEventListener("pointerdown", pointerDown);
    renderer.domElement.addEventListener("pointerup", pointerUp);
    renderer.domElement.addEventListener("pointercancel", cancelPointer);
    renderer.domElement.addEventListener("webglcontextlost", contextError);
    cleanups.push(() => {
      renderer.domElement.removeEventListener("pointerdown", pointerDown);
      renderer.domElement.removeEventListener("pointerup", pointerUp);
      renderer.domElement.removeEventListener("pointercancel", cancelPointer);
      renderer.domElement.removeEventListener("webglcontextlost", contextError);
    });
    const projected = new THREE.Vector3();
    function render(time: number) {
      if (disposed || contextLost) return;
      frame = requestAnimationFrame(render);
      // Keep the office economical on laptops and completely idle in hidden tabs.
      if (document.hidden || time - lastFrame < 1000 / 30) return;
      lastFrame = time;
      controls.enableDamping = !reducedMotion.matches;
      controls.update();
      actors.forEach((actor, id) => {
        const active = actor.working && !reducedMotion.matches;
        actor.root.position.y = .06 + (active ? Math.sin(time * .006) * .025 : 0);
        actor.arms.forEach((arm, i) => { arm.rotation.x = active ? -.3 + Math.sin(time * .012 + i * 2) * .18 : 0; });
        actor.ring.material.opacity = selected === id ? .95 : actor.working ? .65 : .3;
        projected.copy(actor.root.position); projected.y += 1.72; projected.project(camera);
        const label = labels.get(id)!;
        const visible = projected.z > -1 && projected.z < 1 && Math.abs(projected.x) < .96 && Math.abs(projected.y) < .93;
        label.hidden = !visible;
        if (visible) { label.style.left = (projected.x * .5 + .5) * 100 + "%"; label.style.top = (-projected.y * .5 + .5) * 100 + "%"; }
      });
      renderer.render(scene, camera);
    }
    frame = requestAnimationFrame(render);
    return {
      select, view,
      zoom: factor => { camera.zoom = THREE.MathUtils.clamp(camera.zoom * factor, .55, 3); camera.updateProjectionMatrix(); },
      update: (currentMembers, execution) => {
        currentMembers.forEach(agent => {
          const actor = actors.get(agent.id); if (!actor) return;
          const presence = officePresence(agent, execution);
          actor.working = presence.working; actor.light.emissiveIntensity = presence.working ? 1.5 : .1;
          const label = labels.get(agent.id)!; label.dataset.tone = presence.tone;
          label.setAttribute("aria-label", `Seleccionar a ${agent.name}: ${presence.label}`);
          label.title = `${agent.name} · ${presence.label}`;
        });
      },
      dispose: cleanup,
    };
  } catch (error) {
    cleanup();
    throw error;
  }
}
