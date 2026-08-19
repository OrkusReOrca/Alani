// Alani status widget — Three.js scene driven by a small state machine.
// The Python backend broadcasts state over a local WebSocket
// (ws://localhost:8765); this file only ever reacts to what it's told.
//
// NOTE on "morphing": true vertex-level morphing between the idle bar and
// the A glyph would need matched mesh topology between the two shapes,
// which is a lot of authoring effort for a v1. Instead this uses
// crossfade (opacity) + position/scale tweening via GSAP, which reads as
// a smooth morph-like transition without that complexity. Documented as
// a known fidelity gap in the methodology log — worth revisiting with a
// real morph-targets approach later if this doesn't feel smooth enough.

const ACCENT = 0xe8935a;
const ACCENT_LIGHT = 0xf0b088;

const canvas = document.getElementById("scene");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");

const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
renderer.setSize(220, 220);
renderer.setPixelRatio(window.devicePixelRatio);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
camera.position.set(0, 0, 6);

scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const keyLight = new THREE.DirectionalLight(0xffffff, 0.8);
keyLight.position.set(2, 3, 4);
scene.add(keyLight);

// ---------- Bar (idle) ----------
const bar = new THREE.Mesh(
  new THREE.BoxGeometry(1.8, 0.4, 0.25),
  new THREE.MeshStandardMaterial({ color: ACCENT, transparent: true })
);
scene.add(bar);

// ---------- "A" glyph (built procedurally so no font asset is needed) ----------
function buildAShape() {
  const shape = new THREE.Shape();
  // Outer silhouette of a bold, chunky "A" in a roughly -1..1 box.
  shape.moveTo(-0.08, 1.0);
  shape.lineTo(0.08, 1.0);
  shape.lineTo(0.62, -1.0);
  shape.lineTo(0.34, -1.0);
  shape.lineTo(0.22, -0.62);
  shape.lineTo(-0.22, -0.62);
  shape.lineTo(-0.34, -1.0);
  shape.lineTo(-0.62, -1.0);
  shape.closePath();

  const hole = new THREE.Path();
  hole.moveTo(0, 0.5);
  hole.lineTo(0.12, -0.28);
  hole.lineTo(-0.12, -0.28);
  hole.closePath();
  shape.holes.push(hole);

  return shape;
}

const aGlyph = new THREE.Mesh(
  new THREE.ExtrudeGeometry(buildAShape(), { depth: 0.18, bevelEnabled: true, bevelSize: 0.02, bevelThickness: 0.02 }),
  new THREE.MeshStandardMaterial({ color: ACCENT, transparent: true })
);
aGlyph.visible = false;
aGlyph.material.opacity = 0;
scene.add(aGlyph);

// ---------- Star / hourglass / heart — emoji sprites (simplest path to a
// decent-looking icon without modeling/importing 3D assets) ----------
function makeEmojiSprite(emoji) {
  const size = 128;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d");
  ctx.font = `${size * 0.8}px "Segoe UI Emoji"`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(emoji, size / 2, size / 2 + 4);

  const texture = new THREE.CanvasTexture(c);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(0.55, 0.55, 1);
  return sprite;
}

const starSprite = makeEmojiSprite("⭐");
const hourglassSprite = makeEmojiSprite("⌛");
const heartSprite = makeEmojiSprite("❤️");
hourglassSprite.visible = false;
heartSprite.visible = false;
scene.add(starSprite, hourglassSprite, heartSprite);

// ---------- State ----------
let mode = "idle"; // idle | listening_big | listening | speaking | loading | done
let orbitT = 0;
let spinT = 0;
let pulseT = 0;

const CORNER = { x: 0.55, y: -0.55, z: 0 };
const CENTER = { x: 0, y: 0, z: 0 };

function setStatus(text) {
  statusEl.textContent = text;
}

function setTranscript(userText, replyText) {
  let html = "";
  if (userText) html += `<div>${userText}</div>`;
  if (replyText) html += `<div class="reply">${replyText}</div>`;
  transcriptEl.innerHTML = html;
}

function goIdle() {
  mode = "idle";
  setStatus("Standing by...");
  setTranscript("", "");
  gsap.to(bar.material, { opacity: 1, duration: 0.6 });
  bar.visible = true;
  gsap.to(aGlyph.material, { opacity: 0, duration: 0.5, onComplete: () => (aGlyph.visible = false) });
  gsap.to(starSprite.scale, { x: 0.55, y: 0.55, duration: 0.6 });
  hourglassSprite.visible = false;
  heartSprite.visible = false;
  starSprite.visible = true;
}

function goListeningBig() {
  mode = "listening_big";
  setStatus("Listening...");
  bar.visible = true;
  gsap.to(bar.material, { opacity: 0, duration: 0.4, onComplete: () => (bar.visible = false) });
  aGlyph.visible = true;
  aGlyph.scale.set(1.3, 1.3, 1.3);
  aGlyph.position.set(CENTER.x, CENTER.y, CENTER.z);
  gsap.to(aGlyph.material, { opacity: 1, duration: 0.5 });
  gsap.to(aGlyph.scale, { x: 1, y: 1, z: 1, duration: 0.6, ease: "back.out(1.7)" });
  // star docks to the corner and will spin there from now on
  gsap.to(starSprite.position, { x: 1.15, y: 1.15, z: 0, duration: 0.6 });
  gsap.to(starSprite.scale, { x: 0.32, y: 0.32, duration: 0.6 });
  hourglassSprite.visible = false;
  heartSprite.visible = false;
  starSprite.visible = true;
}

function dockAToCorner() {
  gsap.to(aGlyph.scale, { x: 0.55, y: 0.55, z: 0.55, duration: 0.6, ease: "power2.inOut" });
  gsap.to(aGlyph.position, { x: 1.15, y: -1.15, z: 0, duration: 0.6, ease: "power2.inOut" });
}

function goListening(userText) {
  if (mode === "listening_big" && userText) dockAToCorner();
  mode = "listening";
  setStatus("Listening...");
  setTranscript(userText, "");
}

function goSpeaking(userText, replyText) {
  mode = "speaking";
  setStatus("Speaking...");
  setTranscript(userText, replyText);
}

function goLoading() {
  mode = "loading";
  setStatus("Loading...");
  starSprite.visible = false;
  hourglassSprite.visible = true;
  hourglassSprite.position.copy(starSprite.position);
  hourglassSprite.scale.copy(starSprite.scale);
}

function goDone() {
  mode = "done";
  setStatus("Done");
  hourglassSprite.visible = false;
  heartSprite.visible = true;
  heartSprite.position.copy(starSprite.position);
  heartSprite.scale.copy(starSprite.scale);
  setTimeout(goIdle, 1400);
}

function applyServerState(msg) {
  const { state, user_text = "", reply_text = "" } = msg;
  if (state === "idle") return goIdle();
  if (state === "loading") return goLoading();
  if (state === "done") return goDone();
  if (state === "speaking") return goSpeaking(user_text, reply_text);
  if (state === "listening") {
    if (!user_text && mode !== "listening") return goListeningBig();
    return goListening(user_text);
  }
}

// ---------- WebSocket (backend connection) ----------
function connect() {
  const ws = new WebSocket("ws://localhost:8765");
  ws.onmessage = (event) => {
    try {
      applyServerState(JSON.parse(event.data));
    } catch (e) {
      console.error("bad message from backend", e);
    }
  };
  ws.onclose = () => setTimeout(connect, 1500); // backend not up yet / restarted
}
connect();

// ---------- Animation loop ----------
function animate() {
  requestAnimationFrame(animate);

  if (mode === "idle") {
    orbitT += 0.02;
    const radius = 1.1;
    starSprite.position.set(
      Math.cos(orbitT) * radius,
      Math.sin(orbitT) * radius * 0.4 + 0.5,
      Math.sin(orbitT) * radius * 0.3
    );
  } else {
    // star/hourglass/heart spin slowly once docked in the corner
    spinT += 0.02;
    const activeSprite = starSprite.visible ? starSprite : hourglassSprite.visible ? hourglassSprite : heartSprite;
    activeSprite.material.rotation = spinT;
  }

  if (mode === "speaking") {
    // synthetic speech-rhythm pulse (proxy for real TTS amplitude — see
    // methodology log: true audio-reactive pulsing needs the backend to
    // stream amplitude over the socket, left as a follow-up)
    pulseT += 0.25;
    const s = 0.55 + Math.sin(pulseT) * 0.06;
    aGlyph.scale.set(s, s, s);
  }

  bar.rotation.y += 0.003;
  renderer.render(scene, camera);
}
animate();
