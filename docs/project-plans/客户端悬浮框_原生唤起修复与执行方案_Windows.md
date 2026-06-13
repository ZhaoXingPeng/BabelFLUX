# 客户端悬浮框「激活客户端」原生唤起 — 修复与执行方案（Windows）

> 目标：点主页「客户端悬浮框 → 激活客户端」后，真正唤起 **原生 Tauri 悬浮字幕窗** 并接管会话，
> 而不是停在 *"Desktop handoff 未检测到桌面客户端 / 桌面端未响应"*。
>
> 适用环境（本次已确认）：**Windows**；浏览器 + 后端 + 原生客户端 **同机**；本文件只讲「怎么改 / 装什么 / 怎么测」，不直接改 `desktop/`（归 root，避免抢工作区）。

---

## 0. 一句话结论

点按钮后前端确实成功创建了会话、签发了 `lingosync://...&token=h_*` 链接并 `window.location.assign` 了，但**操作系统里没有任何程序真正接管这个协议 + 接管后也取不到 token**，于是浏览器 1.5s 不失焦 → 触发兜底文案。**PR29 只修了"失败兜底 UI"，没修"真正唤起"**。要修需要 4 处改动（3 处在 `desktop/`，1 处后端 CORS）+ 1 处前端体验硬化。

---

## 1. 根因诊断（链路 + 证据）

点击链路：`HomeView.vue:activateDesktop()` → `stores/session.ts:openDesktopFloating()` → `launchDesktopUrl()`：

```
createSession ✅  → issueSessionHandoff ✅（后端返回 lingosync://floating/start?...&token=h_*）
→ window.location.assign(deepLink)   （session.ts:562）
→ armDesktopLaunchFallback()：1500ms 内等 window 'blur' / 'visibilitychange'（session.ts:533-553）
→ 1500ms 到点仍未失焦 → state='fallback'，desktopLaunchMessage='未检测到桌面客户端'
```

`state==='fallback'` 这一事实**反证**了：前半段（建会话 + 发 token）全部成功，后端没问题。卡点 100% 在「`lingosync://` 没被任何已注册程序唤起」。

### 现存 4 个真实缺陷（都不是 PR29 碰过的地方，这正是"没修好"的原因）

| # | 文件 | 问题 | 后果（Windows） |
|---|------|------|------|
| **A** | `desktop/src-tauri/tauri.conf.json` | **完全没有 `plugins.deep-link` 段** | 安装版（NSIS/MSI）不会把 `lingosync://` 写进注册表；`register_all()` 也无 scheme 可注册 |
| **B** | `desktop/src-tauri/src/main.rs` | `tauri_plugin_single_instance` **注册在最后**（应第一个）；其回调**只 `show()`/`focus()`，丢掉 argv 里的新 URL** | `tauri dev` 已在运行时，浏览器再点 → OS 起第二个进程把 URL 放进 argv → 被单实例拦下后 **token 没人转发给 overlay** |
| **C/D** | `desktop/src/App.vue` + `launcherBridge.ts` | 启动时用 `parseLaunchParams(window.location.href)` 取参数 | 在 Tauri 里 `window.location.href` 是 app 自己的页面地址，**不是 deep link**，冷启动拿不到 token → overlay 停在"未携带 handoff token" |
| **E** | `backend/app/core/config.py` | `cors_origins` 只放行 `:5173`(+127)，**没有 `:5175` / Tauri 源** | 修好唤起后**下一个坑**：overlay 的 `fetch` 调 `/handoff/claim` 被 CORS 拒 → "桌面接管失败" |

> 官方依据：**Windows/Linux 上 `onOpenUrl` 离不开 single-instance 插件**（OS 用新进程的命令行参数传 URL）；冷启动必须用 `getCurrent()`，运行中才用 `onOpenUrl`；**单实例插件需第一个注册**。见文末来源。

---

## 2. 要改什么（按"Windows `tauri dev` 演示"必需度排序）

> 演示走 `tauri dev` 时，**B + C/D + E 是端到端跑通的必需项**；A 是安装版分发必需（也建议一并加，因为下面 `register_all()` 依赖它）。F 是你要求的前端体验硬化。

### 改动 A — `desktop/src-tauri/tauri.conf.json`：声明协议 scheme

在顶层（与 `"app"`、`"bundle"` 平级）新增 `"plugins"` 段：

```jsonc
{
  "$schema": "https://schema.tauri.app/config/2",
  "productName": "BabelFlux Floating Caption",
  // ... 现有 app / security / bundle 保持不变 ...
  "plugins": {
    "deep-link": {
      "desktop": {
        "schemes": ["lingosync"]
      }
    }
  }
}
```

作用：安装版据此生成 Windows 注册表项（`HKCU\Software\Classes\lingosync\...`）；`register_all()` 也据此知道要注册哪个 scheme。

### 改动 B — `desktop/src-tauri/src/main.rs`：单实例第一个注册 + 转发 URL

把整个 `main()` 换成：

```rust
use tauri::{Emitter, Manager};

fn main() {
    tauri::Builder::default()
        // ① 单实例必须第一个注册：app 已在运行时，浏览器再点 lingosync:// 会启动第二个进程，
        //    OS 把 URL 放进它的 argv；单实例把它拦回正在运行的实例的这个回调里。
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            if let Some(window) = app.get_webview_window("overlay") {
                let _ = window.show();
                let _ = window.set_focus();
            }
            // ② 从 argv 取出 lingosync:// 链接，转发给前端（换会话 / 二次唤起）
            if let Some(url) = argv.iter().find(|a| a.starts_with("lingosync://")) {
                let _ = app.emit("deep-link-url", url.clone());
            }
        }))
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_store::Builder::new().build())
        .setup(|app| {
            // ③ dev / 未打包：把 conf 里声明的 scheme 注册到当前 exe，
            //    这样不装安装包也能在 `tauri dev` 下被唤起（Windows debug + Linux 生效）。
            #[cfg(any(target_os = "linux", all(debug_assertions, windows)))]
            {
                use tauri_plugin_deep_link::DeepLinkExt;
                let _ = app.deep_link().register_all();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running BabelFlux desktop overlay");
}
```

要点：①单实例移到**第一个**；②回调里把 URL `app.emit("deep-link-url", ...)` 出去（需 `use tauri::Emitter;`）；③`register("lingosync")` 换成 `register_all()`（依赖改动 A 的 conf scheme）。

### 改动 C — `desktop/src/launcherBridge.ts`：新增冷启动取链接

文件末尾新增（保留现有 `parseLaunchParams` / `listenForDeepLinks` 不动）：

```ts
/** 冷启动：app 被 deep link 拉起时，URL 在 getCurrent() 里，而非 window.location */
export async function getLaunchDeepLink(): Promise<LaunchParams | null> {
  try {
    const { getCurrent } = await import("@tauri-apps/plugin-deep-link");
    const urls = await getCurrent();           // string[] | null
    const latest = urls?.at(-1);
    return latest ? parseLaunchParams(latest) : null;
  } catch {
    return null;                               // 浏览器预览无 Tauri → 走原 window.location 分支
  }
}
```

### 改动 D — `desktop/src/App.vue`：三路覆盖（冷启动 / 运行中 / 单实例转发）

把 `onMounted` 改成（并相应在 `onUnmounted` 清理）：

```ts
import { listen } from "@tauri-apps/api/event";
import { getLaunchDeepLink, listenForDeepLinks, parseLaunchParams } from "./launcherBridge";

let cleanupForwarded: (() => void) | null = null;

onMounted(async () => {
  // 运行中（warm）：onOpenUrl
  cleanupDeepLink = await listenForDeepLinks(startFromLaunchParams);
  cleanupShortcut = await registerUnlockShortcut(async () => { /* 原热键逻辑不变 */ });

  // 单实例转发（warm 二次唤起）：监听 Rust emit 的 deep-link-url
  cleanupForwarded = await listen<string>("deep-link-url", (e) =>
    startFromLaunchParams(parseLaunchParams(e.payload))
  );

  // 冷启动：优先 getCurrent()；拿不到再回退浏览器预览的 window.location 解析
  const launched = await getLaunchDeepLink();
  await startFromLaunchParams(launched?.token ? launched : parseLaunchParams());
});

onUnmounted(() => {
  socket?.close();
  cleanupDeepLink?.();
  cleanupShortcut?.();
  cleanupForwarded?.();
});
```

> 这样：**冷启动**走 `getCurrent()`、**运行中**走 `onOpenUrl`、**已运行再唤起**走单实例 `emit` 事件，三种情况都能拿到 token。

### 改动 E — `backend/app/core/config.py`：放行桌面端来源

把 `cors_origins` 属性改为同时放行 overlay 的来源（dev 是 `:5175`，打包后 Windows 是 `http://tauri.localhost`）：

```python
    @property
    def cors_origins(self) -> list[str]:
        origins = {self.frontend_origin}
        if "localhost" in self.frontend_origin:
            origins.add(self.frontend_origin.replace("localhost", "127.0.0.1"))
        elif "127.0.0.1" in self.frontend_origin:
            origins.add(self.frontend_origin.replace("127.0.0.1", "localhost"))
        # 桌面客户端 overlay 的来源：
        #   tauri dev → http://localhost:5175（devUrl）
        #   打包后    → Windows: http://tauri.localhost；macOS/Linux: tauri://localhost
        origins.update({
            "http://localhost:5175",
            "http://127.0.0.1:5175",
            "http://tauri.localhost",
            "tauri://localhost",
        })
        return sorted(origins)
```

> 注意后端 `allow_credentials=True`，所以不能用 `"*"`，必须像上面这样显式列来源。

### 改动 F — 前端体验硬化（你要求的"延长超时 + 我已安装，直接打开"）

**F1. 延长超时** — `frontend/src/stores/session.ts:36`：

```ts
const DESKTOP_LAUNCH_TIMEOUT_MS = 2500; // 1500 → 2500：冷启动 Tauri / 系统确认弹窗常超过 1.5s
```

**F2. 新增"直接打开"动作** — `frontend/src/stores/session.ts`（`continueWithWebFloating` 附近）：

```ts
    // 用户确认已装客户端：重新触发同一个 deep link 并重新计时，而不是当成失败
    reopenDesktop() {
      if (!this.desktopHandoffUrl) {
        this.openDesktopFloating();
        return;
      }
      this.launchDesktopUrl(this.desktopHandoffUrl);
    },
```

**F3. fallback 态加按钮** — `frontend/src/components/workbench/DesktopLaunchPrompt.vue`：

```vue
  <!-- defineEmits 增加 reopen: [] -->
  <button v-if="state === 'fallback'" class="stage-button" type="button" @click="emit('reopen')">
    我已安装，直接打开
  </button>
```

并在 `HomeView.vue` 的 `<DesktopLaunchPrompt @reopen="sessionStore.reopenDesktop" ... />` 接上。

> 可选：把 `window.location.assign` 不必改 —— scheme 注册后 Windows 会弹"打开 BabelFlux Floating Caption?"，点允许即唤起；F1 的更长超时已能覆盖弹窗停留时间。

---

## 3. 需要装什么环境（Windows，全部装在演示这台机器上）

| 组件 | 说明 / 获取 |
|------|------|
| **Rust（含 MSVC 工具链）** | 装 `rustup`（rust-lang.org/tools/install → `rustup-init.exe`），默认即 `x86_64-pc-windows-msvc`，无需额外 target |
| **Microsoft C++ 生成工具** | Visual Studio 2022 **Build Tools**，勾选「使用 C++ 的桌面开发」（含 MSVC v143 + Windows SDK）。否则 Rust 链接报 `link.exe not found` |
| **WebView2 Runtime** | Windows 11 / 较新 Win10 已自带；缺失则装微软「Evergreen WebView2 运行时」 |
| **Node.js** | LTS ≥ 18（建议 20 LTS）。项目用 Vite 6 / vue-tsc 2，需 ≥18 |
| **Python** | ≥ **3.11**（后端用了 `datetime.UTC`），含 pip |
| Tauri CLI | 不用全局装，`desktop/package.json` 已带 `@tauri-apps/cli`，用 `npm run tauri` 即可 |

> 由于仓库目前在这台无头 Linux 机上（无 DISPLAY、无 cargo/webkit），**原生客户端无法在这台机器演示**。请把仓库取到上面这台 Windows 机器上，三件服务都在 Windows 跑。

---

## 4. 怎么跑（同机 3 个终端）

> 先把改动 A–F 应用好，再启动。三个服务都在这台 Windows 上。

**① 后端（FastAPI :8000）**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**② 前端 Web 工作台（Vite :5173）**

```powershell
cd frontend
npm install
npm run dev          # 打开 http://localhost:5173
```

**③ 原生客户端（Tauri，首次会编译 Rust，较慢）**

```powershell
cd desktop
npm install
npm run tauri dev    # 弹出透明 overlay 窗，并把 lingosync:// 注册到当前 exe
```

> 保持 `tauri dev` 一直开着。它既渲染 overlay，又完成了 scheme 注册——这是演示最省事的路径（无需打安装包）。

---

## 5. 怎么测（验证步骤 + 预期）

### 主路径（成功唤起）
1. 三个服务都在跑，浏览器开 `http://localhost:5173`。
2. 点「客户端悬浮框 → 激活客户端」。
3. Windows 可能弹「是否打开 BabelFlux Floating Caption?」→ 允许。（`tauri dev` 已在运行 → 单实例把 URL 转发给现有窗口。）
4. **预期**：overlay 窗里的字幕从 *"Waiting for desktop handoff"* 变成 mock 字幕流并持续滚动；主页提示变 *"已投送到桌面悬浮窗"*（`desktopLaunchState='launched'`），**不再出现 fallback 提示框**。
5. DevTools → Network：`POST /api/sessions/handoff/claim` 返回 **200**（不是 CORS 报错）。

### 兜底路径（确认失败 UI 仍然优雅）
1. 关掉 `tauri dev`（让 scheme 无程序响应）。
2. 再点「激活客户端」。
3. **预期**：约 2.5s 后出现 *"未检测到桌面客户端 / 桌面端未响应"*，并有「我已安装，直接打开」「继续网页悬浮」两个按钮。
4. 点「我已安装，直接打开」→ 重新触发唤起并重新计时（验证 F2/F3）。

### 冷启动路径（验证 C/D 真有效）
1. 关掉 `tauri dev`，但保留 scheme 注册（dev 模式下注册仍在）。或先 build 安装版后整窗关闭。
2. 浏览器点「激活客户端」→ Windows 全新拉起 overlay 进程。
3. **预期**：overlay 不再停在 *"未携带 handoff token"*，而是直接 claim 成功、连上 WS、显示字幕。

---

## 6. 排错对照表

| 现象 | 根因 | 对应改动 |
|------|------|------|
| 点了浏览器毫无反应 / 仍 ~1.5s 后 fallback | scheme 没注册 | 确认 `tauri dev` 在跑；`regedit` 查 `HKCU\Software\Classes\lingosync`；应用 A |
| 弹"打开 BabelFlux?"但 overlay 不显示字幕，停在"未携带 handoff token" | token 没传进去（冷启动读了 window.location；或单实例没转发） | C/D + B |
| overlay 报 *"桌面接管失败"*，Network 见 CORS / blocked | 后端没放行 `:5175` | E |
| overlay 报 claim **404/410** | token 过期（TTL 60s）或已用过 | 唤起要快；或重试。这是预期保护，不是 bug |
| `tauri dev` 编译报 `link.exe not found` / 缺 MSVC | 没装 C++ 生成工具 | 第 3 节 |
| 运行报缺 WebView2 | 缺运行时 | 装 Evergreen WebView2 |
| 二次点「激活客户端」换会话，overlay 不更新 | 单实例回调没转发新 URL | B（`app.emit("deep-link-url", ...)`）+ D（listen 事件）|

---

## 7. 落地顺序（建议）

1. **E（后端 CORS）** —— 改动最小、先消除"修好唤起后才暴露"的隐藏坑。
2. **A + B + C + D（desktop 原生四改）** —— 一起改、一起 `npm run tauri dev` 验证；这是核心。
3. **F（前端硬化）** —— 超时 + "我已安装，直接打开"，提升失败时的可用性。
4. 验证：跑完第 5 节三条路径；`cd backend && python -m pytest`、`cd frontend && npm run build`（含 vue-tsc）、`cd desktop && npm run build`（含 vue-tsc）三处全绿后再提交。

> 注意：`desktop/` 当前归 root 且有并行会话在推进。应用本方案前请先与对方确认无人同时改 `desktop/`，避免冲突。如需我把以上每条改动整理成可直接 `git apply` 的 patch，或改走"Web 弹窗悬浮窗"零安装方案，告诉我即可。

---

## 来源（已核对官方/权威）

- Tauri v2 Deep Linking 插件文档：https://v2.tauri.app/plugin/deep-linking/
- Tauri v2 Deep Link JS 参考（`getCurrent` / `onOpenUrl`）：https://v2.tauri.app/reference/javascript/deep-link/
- Tauri v2 Single Instance 插件：https://v2.tauri.app/plugin/single-instance/
- 插件源码（plugins-workspace v2 分支）：https://github.com/tauri-apps/plugins-workspace/tree/v2/plugins/deep-link
