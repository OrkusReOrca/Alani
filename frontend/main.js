const { app, BrowserWindow } = require("electron");
const path = require("path");

// Small square, always-on-top, frameless status widget — stays out of the
// way but is always visible while the assistant is running.
const WINDOW_SIZE = 220;

function createWindow() {
  const win = new BrowserWindow({
    width: WINDOW_SIZE,
    height: WINDOW_SIZE,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: false,
    webPreferences: {
      contextIsolation: true,
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  win.loadFile(path.join(__dirname, "renderer", "index.html"));
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
