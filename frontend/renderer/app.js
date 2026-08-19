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
// Deliberately more saturated/"maxed out" than a typical UI purple — sleep
// mode should read as unmistakably purple at a glance, not a muted tint.
const COLOR_PURPLE = 0x9d00ff;
const COLOR_GRAY = 0x9e9e9e;

const canvas = document.getElementById("scene");
const statusEl = document.getElementById("status");
const transcriptTextEl = document.getElementById("transcript-text");
const transcriptSpacerEl = document.getElementById("transcript-spacer");
const volumeEl = document.getElementById("volume");
const settingsToggleEl = document.getElementById("settings-toggle");
const settingsPanelEl = document.getElementById("settings-panel");
const inputDeviceEl = document.getElementById("input-device");
const outputDeviceEl = document.getElementById("output-device");
const textSizeEl = document.getElementById("text-size");
const ttsBtnEl = document.getElementById("tts-btn");
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
  updateCornerPositions();
  updateTranscriptSpacer();
}
window.addEventListener("resize", resizeToCanvas);

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

// ---------- "A" glyph (user-supplied artwork, recolored to a flat
// silhouette so the existing orange/purple/gray theming still works) ----------
// aGlyph's aspect ratio isn't 1:1 like the old procedural shape, so every
// place that sets aGlyph.scale needs to account for it — see aScale().
let AGLYPH_ASPECT = 1;
function aScale(base) {
  return { x: base * AGLYPH_ASPECT, y: base, z: base };
}

const aGlyph = new THREE.Sprite(new THREE.SpriteMaterial({ color: COLOR_ORANGE, transparent: true, opacity: 0 }));
aGlyph.visible = false;
scene.add(aGlyph);

// Recolor via canvas: draw the source image, then "source-in" a solid
// white fill so only its alpha (shape + anti-aliased edges) survives —
// the original artwork's own colors are discarded on purpose, so
// material.color (which multiplies against the texture) can fully control
// the glyph's color exactly like the old flat-colored procedural shape did.
const aGlyphImg = new Image();
aGlyphImg.onload = () => {
  const c = document.createElement("canvas");
  c.width = aGlyphImg.width;
  c.height = aGlyphImg.height;
  const ctx = c.getContext("2d");
  ctx.drawImage(aGlyphImg, 0, 0);
  ctx.globalCompositeOperation = "source-in";
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, c.width, c.height);

  const texture = new THREE.CanvasTexture(c);
  aGlyph.material.map = texture;
  aGlyph.material.needsUpdate = true;
  AGLYPH_ASPECT = aGlyphImg.width / aGlyphImg.height;
};
aGlyphImg.src = "assets/a-glyph.png";

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

// Drawn (not emoji) so it reads as a clean gold shape against the light
// window background, rather than whatever tint the system emoji font gives.
function makeGoldStarSprite() {
  const size = 128;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d");

  const cx = size / 2;
  const cy = size / 2;
  const spikes = 5;
  const outerR = size * 0.46;
  const innerR = outerR * 0.42;

  ctx.beginPath();
  for (let i = 0; i < spikes * 2; i++) {
    const r = i % 2 === 0 ? outerR : innerR;
    const angle = (Math.PI / spikes) * i - Math.PI / 2;
    const x = cx + Math.cos(angle) * r;
    const y = cy + Math.sin(angle) * r;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle = "#e8b923";
  ctx.strokeStyle = "#b8890f";
  ctx.lineWidth = 3;
  ctx.fill();
  ctx.stroke();

  const texture = new THREE.CanvasTexture(c);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(0.55, 0.55, 1);
  return sprite;
}

const starSprite = makeGoldStarSprite();
const hourglassSprite = makeEmojiSprite("⌛");
const heartSprite = makeEmojiSprite("❤️");
hourglassSprite.visible = false;
heartSprite.visible = false;
scene.add(starSprite, hourglassSprite, heartSprite);

// ---------- Corner docking (star -> top-right, A -> bottom-right) ----------
// The camera's vertical FOV is fixed, so the visible height at z=0 never
// changes with the window's pixel size — only aspect (width/height)
// changes as the window is resized, which widens/narrows the visible
// width.
//
// Each docked object is placed so its OWN edge sits a fixed EDGE_MARGIN
// from the true frustum edge — not just its center at some fraction of
// the way there. Using one shared fraction for both objects (the first
// attempt at this) clipped the A glyph half off-screen: the A is docked
// noticeably bigger (half-height 0.275 world units) than the tiny corner
// icon (half-height 0.16), so the same fractional inset left enough
// margin for the icon but not enough for the A's own size.
const VERT_HALF_HEIGHT_AT_Z0 = Math.tan(THREE.MathUtils.degToRad(35 / 2)) * 6; // camera: 35deg vertical FOV, z=6
const EDGE_MARGIN_ICON = 0.08; // world units of breathing room from the true edge
// The A reads as sitting "right on the border" at the same tight margin
// the tiny icon uses — it's a much bigger shape, so it needs visibly more
// room to actually look like it has a gap.
const EDGE_MARGIN_A = 0.22;
const ICON_WORLD_DIAMETER = 0.32; // matches starSprite/hourglass/heart's docked scale
const AGLYPH_DOCKED_HALF_HEIGHT = 0.55 / 2; // matches dockAToCorner()'s aScale(0.55)

const CORNER_Y_ICON = VERT_HALF_HEIGHT_AT_Z0 - EDGE_MARGIN_ICON - ICON_WORLD_DIAMETER / 2;
const CORNER_Y_A = VERT_HALF_HEIGHT_AT_Z0 - EDGE_MARGIN_A - AGLYPH_DOCKED_HALF_HEIGHT;
let isADocked = false;

function cornerXIcon() {
  return CORNER_Y_ICON * camera.aspect;
}
function cornerXA() {
  return CORNER_Y_A * camera.aspect;
}

function activeIconSprite() {
  return starSprite.visible ? starSprite : hourglassSprite.visible ? hourglassSprite : heartSprite;
}

// Called on resize (and right after any dock transition) so a window
// resize mid-task doesn't leave the star/A stranded away from the corner.
function updateCornerPositions() {
  if (mode !== "idle") {
    const icon = activeIconSprite();
    icon.position.x = cornerXIcon();
    icon.position.y = CORNER_Y_ICON;
  }
  if (isADocked) {
    aGlyph.position.x = cornerXA();
    aGlyph.position.y = -CORNER_Y_A;
  }
}

// The docked icon (star/hourglass/heart) is rendered in 3D, but the
// transcript text wraps around it via a plain floated DOM element
// (#transcript-spacer — see index.html/style.css). That spacer has to be
// sized/positioned in real screen pixels to actually line up with where
// the icon lands on screen, which moves with the window size — so it's
// computed here from the same fixed frustum math as the corner docking,
// instead of a guessed constant that only matched one window size.
const TRANSCRIPT_TOP_PX = 26; // must match #transcript's CSS "top"
function updateTranscriptSpacer() {
  const canvasH = canvas.clientHeight;
  if (!canvasH) return;
  const pxPerWorldUnit = canvasH / (2 * VERT_HALF_HEIGHT_AT_Z0);
  const iconDiameterPx = ICON_WORLD_DIAMETER * pxPerWorldUnit;
  const iconCenterYPx = (VERT_HALF_HEIGHT_AT_Z0 - CORNER_Y_ICON) * pxPerWorldUnit;
  const pad = 6;
  const marginTop = Math.max(0, Math.round(iconCenterYPx - iconDiameterPx / 2 - TRANSCRIPT_TOP_PX - pad));
  const size = Math.round(iconDiameterPx + pad * 2);
  transcriptSpacerEl.style.marginTop = `${marginTop}px`;
  transcriptSpacerEl.style.width = `${size}px`;
  transcriptSpacerEl.style.height = `${size}px`;
}

// ---------- State ----------
let mode = "starting"; // starting | idle | listening_big | listening | speaking | loading | done
let orbitT = 0;
let spinT = 0;
let powerOn = true;
let sleepMode = false;

// Speaking pulse: driven by the real TTS output level (see tts.py's
// "amplitude" broadcast), not a synthetic rhythm. ampTarget is the latest
// value from the backend; ampSmoothed eases toward it each frame so the
// glyph doesn't jitter at the audio-callback rate — this is also what
// makes the expand/contract feel slow and speech-matched rather than
// twitchy.
let ampTarget = 0;
let ampSmoothed = 0;

function setStatus(text) {
  statusEl.textContent = text;
}

function setTranscript(userText, replyText) {
  let html = "";
  if (userText) html += `<div>${userText}</div>`;
  if (replyText) html += `<div class="reply">${replyText}</div>`;
  transcriptTextEl.innerHTML = html;
}

function currentBarColor() {
  if (!powerOn) return COLOR_GRAY;
  if (sleepMode) return COLOR_PURPLE;
  return COLOR_ORANGE;
}

// The A glyph can be on-screen (listening/loading/speaking/done) when
// sleep gets toggled, so its color needs to update immediately rather
// than waiting for the next goIdle()/goListeningBig() call.
function updateAGlyphColor() {
  aGlyph.material.color.set(!powerOn ? COLOR_GRAY : sleepMode ? COLOR_PURPLE : COLOR_ORANGE);
}

// Shown from page load until the backend confirms the wake-word listener
// has actually finished loading (see main.py) — model loading takes a
// few real seconds, and without this the UI used to claim "Standing by"
// (implying it's already listening) before that was actually true.
function goStarting() {
  mode = "starting";
  isADocked = false;
  setStatus("Starting up...");
  setTranscript("", "");
  bar.material.color.set(COLOR_GRAY);
  bar.material.opacity = 1;
  bar.visible = true;
  aGlyph.visible = false;
  aGlyph.material.opacity = 0;
  starSprite.visible = false;
  hourglassSprite.visible = false;
  heartSprite.visible = false;
}

function goIdle() {
  mode = "idle";
  isADocked = false;
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
  isADocked = false;
  setStatus("Listening...");
  // Only the very first idle -> listening_big transition needs to fade the
  // bar out; on later turns (speaking -> listening_big again, no idle in
  // between) it's already faded/hidden. Unconditionally re-showing it here
  // used to force a fresh render of the bar mesh every time — its
  // directional-light specular highlight would flash across the screen
  // for a frame or two before the opacity tween caught up again, which is
  // the "white bar crosses the A" glitch on every return to listening.
  if (bar.visible) {
    gsap.to(bar.material, { opacity: 0, duration: 0.4, onComplete: () => (bar.visible = false) });
  }
  updateAGlyphColor();
  aGlyph.visible = true;
  const big = aScale(1.3);
  aGlyph.scale.set(big.x, big.y, big.z);
  aGlyph.position.set(0, 0, 0.3); // slightly in front of the bar's z=0 plane, avoids z-fighting
  gsap.to(aGlyph.material, { opacity: 1, duration: 0.5 });
  gsap.to(aGlyph.scale, { ...aScale(1), duration: 0.6, ease: "back.out(1.7)" });
  gsap.to(starSprite.position, { x: cornerXIcon(), y: CORNER_Y_ICON, z: 0, duration: 0.6 });
  gsap.to(starSprite.scale, { x: 0.32, y: 0.32, duration: 0.6 });
  hourglassSprite.visible = false;
  heartSprite.visible = false;
  starSprite.visible = true;
}

function dockAToCorner() {
  isADocked = true;
  gsap.to(aGlyph.scale, { ...aScale(0.55), duration: 0.6, ease: "power2.inOut" });
  gsap.to(aGlyph.position, { x: cornerXA(), y: -CORNER_Y_A, z: 0.3, duration: 0.6, ease: "power2.inOut" });
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
  ampTarget = 0;
  ampSmoothed = 0;
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
  if (state === "starting") return goStarting();
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
  const wasPowerOn = powerOn;
  powerOn = s.power_on;
  sleepMode = s.sleep_mode;

  volumeEl.value = s.volume;
  if (inputDeviceEl.dataset.loaded) inputDeviceEl.value = s.input_device ?? "";
  if (outputDeviceEl.dataset.loaded) outputDeviceEl.value = s.output_device ?? "";
  textSizeEl.value = s.text_size;
  transcriptTextEl.style.fontSize = `${s.text_size}px`;

  sleepBtnEl.classList.toggle("active", sleepMode);
  powerBtnEl.classList.toggle("off", !powerOn);
  ttsBtnEl.classList.toggle("off", !s.tts_enabled);

  // Power off must cut over instantly even mid-task — don't wait for the
  // backend to finish its current turn and broadcast "idle" itself.
  if (wasPowerOn && !powerOn) {
    goIdle();
    return;
  }

  // Sleep can be toggled mid-task too; the A (if currently on screen)
  // should recolor right away rather than waiting for the next state
  // change, even though the task itself keeps running to completion.
  if (aGlyph.visible) updateAGlyphColor();

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
      else if (msg.type === "amplitude") ampTarget = msg.value;
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
textSizeEl.addEventListener("input", () => {
  const value = parseInt(textSizeEl.value, 10);
  transcriptTextEl.style.fontSize = `${value}px`; // live preview, no waiting for the backend round-trip
  send({ type: "set_text_size", value });
});
settingsToggleEl.addEventListener("click", () => settingsPanelEl.classList.toggle("hidden"));
ttsBtnEl.addEventListener("click", () => send({ type: "toggle_tts" }));
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
    // Ease toward the latest real TTS output level rather than jumping
    // straight to it — a low easing factor is what makes this read as a
    // slow, natural swell/settle instead of a twitchy per-block jump.
    ampSmoothed += (ampTarget - ampSmoothed) * 0.06;
    const s = aScale(0.55 + Math.min(ampSmoothed * 1.4, 0.22));
    aGlyph.scale.set(s.x, s.y, s.z);
  }

  renderer.render(scene, camera);
}
goStarting();
resizeToCanvas();
animate();
