"""Stealth patches injected into every page before any site script runs.

Targets the most common bot-detection signals: navigator.webdriver, plugins,
languages, permissions, chrome runtime, WebGL vendor/renderer, canvas noise,
audio fingerprint, hardware concurrency, and CDP traces.
"""

STEALTH_JS = r"""
(() => {
  // --- navigator.webdriver ---
  try {
    Object.defineProperty(Navigator.prototype, 'webdriver', {
      get: () => undefined,
      configurable: true,
    });
  } catch (e) {}

  // --- window.chrome runtime stub ---
  if (!window.chrome) {
    window.chrome = {};
  }
  window.chrome.runtime = window.chrome.runtime || {
    PlatformOs: { MAC: 'mac', WIN: 'win', ANDROID: 'android', CROS: 'cros', LINUX: 'linux', OPENBSD: 'openbsd' },
    PlatformArch: { ARM: 'arm', X86_32: 'x86-32', X86_64: 'x86-64' },
    RequestUpdateCheckStatus: { THROTTLED: 'throttled', NO_UPDATE: 'no_update', UPDATE_AVAILABLE: 'update_available' },
    OnInstalledReason: { INSTALL: 'install', UPDATE: 'update', CHROME_UPDATE: 'chrome_update', SHARED_MODULE_UPDATE: 'shared_module_update' },
    OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
    connect: () => {},
    sendMessage: () => {},
  };
  window.chrome.app = window.chrome.app || {
    isInstalled: false,
    InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
    RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
  };

  // --- navigator.permissions.query (Notification quirk) ---
  try {
    const origQuery = navigator.permissions && navigator.permissions.query;
    if (origQuery) {
      navigator.permissions.query = (params) =>
        params && params.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission, onchange: null })
          : origQuery.call(navigator.permissions, params);
    }
  } catch (e) {}

  // --- navigator.plugins / mimeTypes (non-empty, headless detector) ---
  try {
    const fakePlugin = (name, filename, desc) => {
      const p = Object.create(Plugin.prototype);
      Object.defineProperties(p, {
        name: { value: name },
        filename: { value: filename },
        description: { value: desc },
        length: { value: 1 },
      });
      return p;
    };
    const plugins = [
      fakePlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      fakePlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      fakePlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      fakePlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format'),
      fakePlugin('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format'),
    ];
    Object.setPrototypeOf(plugins, PluginArray.prototype);
    Object.defineProperty(Navigator.prototype, 'plugins', {
      get: () => plugins,
      configurable: true,
    });
    Object.defineProperty(Navigator.prototype, 'mimeTypes', {
      get: () => {
        const arr = [{ type: 'application/pdf', suffixes: 'pdf', description: '' }];
        Object.setPrototypeOf(arr, MimeTypeArray.prototype);
        return arr;
      },
      configurable: true,
    });
  } catch (e) {}

  // --- navigator.languages ---
  try {
    const langs = window.__BG_LANGS__ || ['en-US', 'en'];
    Object.defineProperty(Navigator.prototype, 'languages', {
      get: () => langs,
      configurable: true,
    });
  } catch (e) {}

  // --- hardwareConcurrency / deviceMemory ---
  try {
    Object.defineProperty(Navigator.prototype, 'hardwareConcurrency', {
      get: () => window.__BG_CORES__ || 8,
      configurable: true,
    });
    Object.defineProperty(Navigator.prototype, 'deviceMemory', {
      get: () => window.__BG_MEM__ || 8,
      configurable: true,
    });
  } catch (e) {}

  // --- navigator.platform / userAgentData consistency ---
  try {
    if (window.__BG_PLATFORM__) {
      Object.defineProperty(Navigator.prototype, 'platform', {
        get: () => window.__BG_PLATFORM__,
        configurable: true,
      });
    }
  } catch (e) {}

  // --- WebGL vendor / renderer ---
  try {
    const vendor = window.__BG_GL_VENDOR__ || 'Intel Inc.';
    const renderer = window.__BG_GL_RENDERER__ || 'Intel Iris OpenGL Engine';
    const patch = (proto) => {
      const orig = proto.getParameter;
      proto.getParameter = function (param) {
        if (param === 37445) return vendor;   // UNMASKED_VENDOR_WEBGL
        if (param === 37446) return renderer; // UNMASKED_RENDERER_WEBGL
        return orig.call(this, param);
      };
    };
    if (window.WebGLRenderingContext) patch(WebGLRenderingContext.prototype);
    if (window.WebGL2RenderingContext) patch(WebGL2RenderingContext.prototype);
  } catch (e) {}

  // --- Canvas fingerprint noise (subtle, deterministic per session) ---
  try {
    const seed = window.__BG_CANVAS_SEED__ || 0.0000123;
    const toBlob = HTMLCanvasElement.prototype.toBlob;
    const toDataURL = HTMLCanvasElement.prototype.toDataURL;
    const getImageData = CanvasRenderingContext2D.prototype.getImageData;
    const noisify = (canvas, ctx) => {
      try {
        const w = canvas.width, h = canvas.height;
        if (!w || !h) return;
        const img = ctx.getImageData(0, 0, w, h);
        for (let i = 0; i < img.data.length; i += 4) {
          img.data[i]     = img.data[i]     ^ ((seed * 255) & 1);
          img.data[i + 1] = img.data[i + 1] ^ ((seed * 255) & 1);
          img.data[i + 2] = img.data[i + 2] ^ ((seed * 255) & 1);
        }
        ctx.putImageData(img, 0, 0);
      } catch (e) {}
    };
    HTMLCanvasElement.prototype.toBlob = function (...args) {
      const ctx = this.getContext('2d'); if (ctx) noisify(this, ctx);
      return toBlob.apply(this, args);
    };
    HTMLCanvasElement.prototype.toDataURL = function (...args) {
      const ctx = this.getContext('2d'); if (ctx) noisify(this, ctx);
      return toDataURL.apply(this, args);
    };
    CanvasRenderingContext2D.prototype.getImageData = function (...args) {
      const data = getImageData.apply(this, args);
      for (let i = 0; i < data.data.length; i += 97) {
        data.data[i] = data.data[i] ^ ((seed * 255) & 1);
      }
      return data;
    };
  } catch (e) {}

  // --- AudioContext fingerprint noise ---
  try {
    const orig = AnalyserNode.prototype.getFloatFrequencyData;
    AnalyserNode.prototype.getFloatFrequencyData = function (arr) {
      orig.call(this, arr);
      for (let i = 0; i < arr.length; i++) arr[i] += (Math.random() - 0.5) * 1e-7;
      return arr;
    };
  } catch (e) {}

  // --- Battery API stub (some detectors flag missing) ---
  try {
    if (!navigator.getBattery) {
      navigator.getBattery = () => Promise.resolve({
        charging: true, chargingTime: 0, dischargingTime: Infinity, level: 1,
        addEventListener: () => {}, removeEventListener: () => {},
      });
    }
  } catch (e) {}

  // --- Screen depth ---
  try {
    Object.defineProperty(Screen.prototype, 'colorDepth', { get: () => 24, configurable: true });
    Object.defineProperty(Screen.prototype, 'pixelDepth', { get: () => 24, configurable: true });
  } catch (e) {}

  // --- Hide CDP traces (Runtime.enable detector) ---
  try {
    const errToString = Error.prototype.toString;
    Error.prototype.toString = function () {
      const s = errToString.call(this);
      return s.replace(/\n\s*at .*puppeteer.*$/gm, '').replace(/\n\s*at .*playwright.*$/gm, '');
    };
  } catch (e) {}

  // --- iframe contentWindow trap (some checks recurse into frames) ---
  try {
    const orig = HTMLIFrameElement.prototype.__lookupGetter__('contentWindow');
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
      get: function () {
        const win = orig.call(this);
        try {
          if (win) Object.defineProperty(win.navigator, 'webdriver', { get: () => undefined });
        } catch (e) {}
        return win;
      },
      configurable: true,
    });
  } catch (e) {}

  // --- toString patches so .toString() of overridden funcs looks native ---
  try {
    const native = Function.prototype.toString;
    const map = new WeakMap();
    Function.prototype.toString = function () {
      if (map.has(this)) return map.get(this);
      return native.call(this);
    };
    window.__BG_MARK_NATIVE__ = (fn, name) => {
      map.set(fn, `function ${name}() { [native code] }`);
    };
  } catch (e) {}
})();
"""
