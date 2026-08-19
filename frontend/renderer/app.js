// Alani status widget — Three.js scene driven by a small state machine.
// The Python backend broadcasts state/settings/devices over a local
// WebSocket (ws://localhost:8765) and accepts commands back the same way;
// this file only ever reacts to what it's told, and never assumes a
// setting took effect until the backend confirms it via a "settings"
// message.
//
// NOTE on "morphing": true vertex-level morphing between the idle bar and
// the A glyph would need matched mesh topology between the two shapes,
// which is a lot of authoring effort for a v1. Instead this uses
// crossfade (opacity) + position/scale tweening via GSAP, which reads as
// a smooth morph-like transition without that complexity.

const THREE = require("three");
const { gsap } = require("gsap");

const COLOR_ORANGE = 0xe8935a;
const COLOR_PURPLE = 0x8b5cf6;
const COLOR_GRAY = 0x9e9e9e;

const canvas = document.getElementById("scene");
const statusEl = document.getElementById("status");
const transcriptEl = document.getElementById("transcript");
const volumeEl = document.getElementById("volume");
const settingsToggleEl = document.getElementById("settings-toggle");
const settingsPanelEl = document.getElementById("settings-panel");
const inputDeviceEl = document.getElementById("input-device");
const outputDeviceEl = document.getElementById("output-device");
const sleepBtnEl = document.getElementById("sleep-btn");
const powerBtnEl = document.getElementById("power-btn");

const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
camera.position.set(0, 0, 6);

// The window is resizable now (was fixed 220x220) — keep the scene sized
// to whatever the canvas's CSS box actually is, and keep the bar/star
// centered regardless of aspect ratio.
function resizeToCanvas() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (width === 0 || height === 0) return;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resizeToCanvas);
resizeToCanvas();

scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const keyLight = new THREE.DirectionalLight(0xffffff, 0.8);
keyLight.position.set(2, 3, 4);
scene.add(keyLight);

// ---------- Bar (idle) ----------
const bar = new THREE.Mesh(
  new THREE.BoxGeometry(1.8, 0.4, 0.25),
  new THREE.MeshStandardMaterial({ color: COLOR_ORANGE, transparent: true })
);
scene.add(bar);

// ---------- "A" glyph (built procedurally so no font asset is needed) ----------
function buildAShape() {
  const shape = new THREE.Shape();
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
  new THREE.MeshStandardMaterial({ color: COLOR_ORANGE, transparent: true })
);
aGlyph.visible = false;
aGlyph.material.opacity = 0;
scene.add(aGlyph);

// ---------- Star / hourglass / heart — emoji sprites ----------
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
let powerOn = true;
let sleepMode = false;

function setStatus(text) {
  statusEl.textContent = text;
}

function setTranscript(userText, replyText) {
  let html = "";
  if (userText) html += `<div>${userText}</div>`;
  if (replyText) html += `<div class="reply">${replyText}</div>`;
  transcriptEl.innerHTML = html;
}

function currentBarColor() {
  if (!powerOn) return COLOR_GRAY;
  if (sleepMode) return COLOR_PURPLE;
  return COLOR_ORANGE;
}

function goIdle() {
  mode = "idle";
  setStatus(!powerOn ? "Powered off" : sleepMode ? "Sleeping..." : "Standing by...");
  setTranscript("", "");
  bar.material.color.set(currentBarColor());
  gsap.to(bar.material, { opacity: 1, duration: 0.6 });
  bar.visible = true;
  gsap.to(aGlyph.material, { opacity: 0, duration: 0.5, onComplete: () => (aGlyph.visible = false) });
  gsap.to(starSprite.scale, { x: 0.55, y: 0.55, duration: 0.6 });
  hourglassSprite.visible = false;
  heartSprite.visible = false;
  starSprite.visible = powerOn; // frozen/hidden while powered off — see animate()
}

function goListeningBig() {
  mode = "listening_big";
  setStatus("Listening...");
  bar.visible = true;
  gsap.to(bar.material, { opacity: 0, duration: 0.4, onComplete: () => (bar.visible = false) });
  aGlyph.material.color.set(COLOR_ORANGE);
  aGlyph.visible = true;
  aGlyph.scale.set(1.3, 1.3, 1.3);
  aGlyph.position.set(0, 0, 0);
  gsap.to(aGlyph.material, { opacity: 1, duration: 0.5 });
  gsap.to(aGlyph.scale, { x: 1, y: 1, z: 1, duration: 0.6, ease: "back.out(1.7)" });
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

function applySettings(s) {
  powerOn = s.power_on;
  sleepMode = s.sleep_mode;

  volumeEl.value = s.volume;
  if (inputDeviceEl.dataset.loaded) inputDeviceEl.value = s.input_device ?? "";
  if (outputDeviceEl.dataset.loaded) outputDeviceEl.value = s.output_device ?? "";

  sleepBtnEl.classList.toggle("active", sleepMode);
  powerBtnEl.classList.toggle("off", !powerOn);

  if (mode === "idle") goIdle(); // re-color the bar / update status text immediately
}

function applyDevices(msg) {
  const fillSelect = (el, devices) => {
    el.innerHTML = '<option value="">System default</option>';
    for (const d of devices) {
      const opt = document.createElement("option");
      opt.value = d.index;
      opt.textContent = d.name;
      el.appendChild(opt);
    }
    el.dataset.loaded = "1";
  };
  fillSelect(inputDeviceEl, msg.inputs);
  fillSelect(outputDeviceEl, msg.outputs);
}

// ---------- WebSocket (backend connection) ----------
let ws = null;

function send(payload) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(payload));
}

function connect() {
  ws = new WebSocket("ws://localhost:8765");
  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "state") applyServerState(msg);
      else if (msg.type === "settings") applySettings(msg);
      else if (msg.type === "devices") applyDevices(msg);
    } catch (e) {
      console.error("bad message from backend", e);
    }
  };
  ws.onclose = () => setTimeout(connect, 1500); // backend not up yet / restarted
}
connect();

// ---------- UI control wiring ----------
volumeEl.addEventListener("input", () => send({ type: "set_volume", value: parseFloat(volumeEl.value) }));
inputDeviceEl.addEventListener("change", () => {
  const value = inputDeviceEl.value === "" ? null : parseInt(inputDeviceEl.value, 10);
  send({ type: "set_input_device", value });
});
outputDeviceEl.addEventListener("change", () => {
  const value = outputDeviceEl.value === "" ? null : parseInt(outputDeviceEl.value, 10);
  send({ type: "set_output_device", value });
});
settingsToggleEl.addEventListener("click", () => settingsPanelEl.classList.toggle("hidden"));
sleepBtnEl.addEventListener("click", () => send({ type: "toggle_sleep" }));
powerBtnEl.addEventListener("click", () => send({ type: "toggle_power" }));

// ---------- Animation loop ----------
function animate() {
  requestAnimationFrame(animate);

  if (mode === "idle" && powerOn) {
    // Vertical loop through the bar — top, then front, then under, then
    // behind, back to top (NASA-logo-style), bar itself stays still.
    // y = cos, z = sin: t=0 top, t=90deg front, t=180deg under, t=270deg
    // behind. WebGL depth-tests the sprite against the bar automatically,
    // so it's correctly hidden while passing behind.
    orbitT += 0.025;
    const radius = 0.85;
    starSprite.position.set(0, Math.cos(orbitT) * radius, Math.sin(orbitT) * radius);
  } else if (mode !== "idle") {
    // star/hourglass/heart spin slowly once docked in the corner
    spinT += 0.02;
    const activeSprite = starSprite.visible ? starSprite : hourglassSprite.visible ? hourglassSprite : heartSprite;
    activeSprite.material.rotation = spinT;
  }
  // powered off + idle: star frozen/hidden, bar gray, nothing animates — intentional

  if (mode === "speaking") {
    // synthetic speech-rhythm pulse (proxy for real TTS amplitude — see
    // methodology log: true audio-reactive pulsing needs the backend to
    // stream amplitude over the socket, left as a follow-up)
    pulseT += 0.25;
    const s = 0.55 + Math.sin(pulseT) * 0.06;
    aGlyph.scale.set(s, s, s);
  }

  renderer.render(scene, camera);
}
animate();
