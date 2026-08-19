const { app, BrowserWindow } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const fs = require("fs");

// Small square, always-on-top, frameless status widget — stays out of the
// way but is always visible while the assistant is running.
const WINDOW_SIZE = 220;

const REPO_ROOT = path.join(__dirname, "..");
const BACKEND_PYTHON = path.join(REPO_ROOT, "venv", "Scripts", "python.exe");
const BACKEND_MAIN = path.join(REPO_ROOT, "src", "main.py");

let backendProcess = null;

function startBackend() {
  if (!fs.existsSync(BACKEND_PYTHON)) {
    console.error(
      `[alani] backend venv not found at ${BACKEND_PYTHON} — the UI will still open, ` +
        `but nothing will actually listen/respond until the backend is set up (see README).`
    );
    return;
  }

  console.log("[alani] starting backend...");
  backendProcess = spawn(BACKEND_PYTHON, ["-u", "main.py"], {
    cwd: path.join(REPO_ROOT, "src"),
  });

  backendProcess.stdout.on("data", (data) => process.stdout.write(`[backend] ${data}`));
  backendProcess.stderr.on("data", (data) => process.stderr.write(`[backend] ${data}`));
  backendProcess.on("exit", (code) => {
    console.log(`[alani] backend exited (code ${code})`);
    backendProcess = null;
  });
}

function stopBackend() {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: WINDOW_SIZE,
    height: WINDOW_SIZE,
    frame: true,
    backgroundColor: "#f0f0f0",
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: false,
    webPreferences: {
      // Trusted, fully local content only (no remote pages ever loaded in
      // this window) — nodeIntegration is a deliberate, contained choice
      // here to sidestep ES-module-over-file:// loading quirks, not
      // something to copy into a window that ever shows remote/untrusted
      // content.
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(() => {
  // Register to auto-launch at Windows login. Reliable once packaged as a
  // real installed .exe (electron-builder etc); in unpackaged dev mode
  // this sets a login item pointing at Electron's own binary, which is
  // enough for `npm start`-style usage but worth re-checking after
  // packaging — see methodology log.
  app.setLoginItemSettings({ openAtLogin: true });

  startBackend();
  createWindow();
});

app.on("window-all-closed", () => {
  stopBackend();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", stopBackend);
