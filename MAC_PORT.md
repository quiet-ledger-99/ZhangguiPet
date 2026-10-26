# 掌柜台桌宠 · macOS 移植说明（v0.3.10）

目标：同一份源码在 Windows 上行为**完全不变**，在 macOS（Apple Silicon，已在 macOS 27 / Mac mini 上跑过）上能正常显示、托盘（菜单栏）、隐藏/探头、单实例、登录自启。
Windows 打包文件（`packaging/build_win.ps1`、`zhanggui_pet.spec`、`version_info.txt`）一个字没改。

## 开发环境（venv 放在源码树外面）

```bash
cd ~/Projects/ZhangguiPet-mac
uv venv -p 3.12 .venv
uv pip install --python .venv/bin/python PySide6-Essentials==6.10.3   # 跑源码只要这个
uv pip install --python .venv/bin/python pyinstaller                  # 打 .app 才需要（测过 6.22.3）
cd src && ../.venv/bin/python zhanggui_pet.py
```

调试用环境变量和 Windows 一样：`ZHANGGUI_PET_DEBUG=1`、`ZHANGGUI_PET_CONFIG_DIR=/tmp/xxx`、`ZHANGGUI_PET_AUTOQUIT=秒`、`ZHANGGUI_PET_NO_DIALOG=1`、`ZHANGGUI_PET_CMD_FILE=…`。
单元测试：`QT_QPA_PLATFORM=offscreen ../.venv/bin/python tests/test_v039.py`（v035–v039、samesize 都能跑）。

## Windows 专用代码盘点 → macOS 怎么处理

| 位置 | Windows 做法 | macOS |
|---|---|---|
| `zhanggui_pet.friendly_box` | `windll.user32.MessageBoxW` | `osascript display dialog`（新增） |
| 崩溃提示 | “把 ZhangguiPet.exe 加进信任” | macOS 上不说这句 |
| `pet_platform.SingleInstance` | 命名 Mutex + Event 唤醒 | 原本就有 QLockFile + 本地文件唤醒的非 Windows 分支，直接可用（已测：第二次打开 → 第一只说“我一直都在呀”） |
| `pet_platform.idle_seconds` | `GetLastInputInfo` | `CoreGraphics.CGEventSourceSecondsSinceLastEventType`（新增，不需要任何权限） |
| `pet_platform.fullscreen_on_my_monitor` | 枚举 HWND 判断全屏 | 返回 False；改用窗口 collectionBehavior：全屏 App 自己占一个 Space，桌宠不带 FullScreenAuxiliary 就不会叠上去 |
| 开机自启 | `winreg` HKCU\…\Run | `~/Library/LaunchAgents/local.ZhangguiPet.plist`（RunAtLoad；.app 时用 `/usr/bin/open X.app`）。菜单名“登录时自动启动” |
| 配置目录 | `%APPDATA%\ZhangguiPet` | `~/Library/Application Support/ZhangguiPet` |
| 语音 | `winsound` | 先探测 `afplay`（`which`，再看 `/usr/bin/afplay`），没有再试 paplay / aplay / ffplay。发布包里没有语音包，所以日志是 `voice none`，属正常 |
| 低权限目录检测（integrity level） | Windows 专用 | 不适用（日志显示 `integrity ?`） |
| 字体 | 微软雅黑 | 苹方 PingFang SC 放第一（省掉 Qt 找不到雅黑时 100ms 的字体别名扫描） |
| 托盘 | 右下角通知区，单击显示/隐藏 | 菜单栏 NSStatusItem；macOS 上单击就是弹菜单，所以单击不再切换显示，菜单里本来就有“显示她/先藏起来”；Mac 上**不用** `setContextMenu`（macOS 27 + Qt 6.10.3 下一点图标就抛 NSException 闪退：菜单开始跟踪时 Qt 对 KitDefined 事件调了 `clickCount`），改成 `activated` 里自己 `tray_menu.popup()` 在图标下方；所有“右下角托盘”文案在 Mac 上改成“菜单栏” |
| Dock 图标 | 无（Qt.Tool） | `pet_macos.hide_dock_icon()`：NSApp `setActivationPolicy:Accessory`；打包时 Info.plist `LSUIElement` |
| 窗口 | Frameless+Tool+StaysOnTop | 同上 + `WA_MacAlwaysShowToolWindow`（不然 App 失去前台就藏）+ `pet_macos.tune_pet_window`：所有 Space 可见、Stationary、不进 Cmd+` 轮换、`setHidesOnDeactivate:NO`。每次 showEvent 重新设置（切置顶会重建原生窗口） |
| 拖进来的“程序”文件 | exe msi bat … | 另外认 dmg pkg command |
| 打包 | PyInstaller onedir + zip，图标 .ico | 新增 `packaging/zhanggui_pet_mac.spec` + `packaging/build_mac.sh`：.app（arm64，ad-hoc 签名）+ zip，图标用 `sips`/`iconutil` 从 `assets/icon.png` 现做 |
| `pet_brain` | 全部离线 | 没有平台相关代码，不用改 |

## 改动的文件

- `pet_platform.py`：`IS_MAC`、配置目录、空闲时间、LaunchAgent 自启、`autostart_supported()`、afplay。
- `pet_macos.py`（新）：ctypes 调 Objective-C 运行时（不依赖 pyobjc）。只在 Qt 的 `cocoa` 平台插件下生效，offscreen 测试时什么也不做。
- `zhanggui_pet.py`：弹窗、字体、窗口属性、showEvent、托盘点击和文案、自启菜单、启动时隐藏 Dock 图标。
- `pet_lines.py`：首次提示 `first02` 的 Mac 文案；drop_exe 扩展名。
- `packaging/zhanggui_pet_mac.spec`、`packaging/build_mac.sh`（新）。

## 已验证（Mac mini，macOS 27.0.1，arm64，1920×1080）

- 源码运行：窗口透明无边框、置顶，右下角正常显示，气泡用苹方；`lsappinfo` 显示 `type="UIElement"`（Dock 无图标）。
- 菜单栏图标出现（`tray check visible True`）。
- 隐藏 → 显示（菜单 / dev 命令 `toggle_hidden`）正常；左边探头（`peek_side=left`）位置正常。
- 单实例：第二次打开立刻退出，第一只被唤醒。
- 单元测试 v035/v036/v037/v039/samesize 全过；v038 的 `test_06_floating_assets_unchanged` 在**未改动的** v0.3.9 基线上也失败（素材哈希和 v0.3.8 不同，跟移植无关）。

## 还没做 / 已知问题

- 探头的边缘判定没在真实拖拽下测：macOS 的菜单栏（顶）和 Dock（底/侧）由 `availableGeometry` 扣掉，`PEEK_ENABLE_TOP=False` 顶部本来就关；Dock 在左右两侧时需要人手拖一下看看。
- 菜单栏图标是彩色 PNG，不是 macOS 推荐的单色 template 图标（深色/浅色菜单栏都能看见，但不够“原生”）。
- 气泡通知 `QSystemTrayIcon.showMessage` 在 macOS 上走系统通知，第一次可能要用户允许通知，未打包时显示为 Python。
- .app：未用开发者证书签名、未公证。别人下载后 Gatekeeper 会拦，需要右键→打开，或 `xattr -dr com.apple.quarantine ZhangguiPet.app`。正式分发要 Developer ID + `notarytool`。
- 只打了 arm64；Intel Mac 需要另打或 universal2（PySide6 wheel 需要对应架构）。
- 多显示器、Retina（2x）没测（测试机是 1x 单屏）。

## 本机助手通道（M1，默认关）

源码运行时菜单有「高级 → 允许本机助手控制我（实验）」。默认不勾。勾上才听 `127.0.0.1:6710`（`settings.json` 的 `control_port` 可改）。口令在配置目录 `control_token`，权限 600。打包后的 .app 默认不显示这项，除非 `show_control_menu` 为 true。

```bash
python3 tools/pet_ctl.py status
python3 tools/pet_ctl.py say --json-base64 <标准 base64 的 UTF-8 JSON>
QT_QPA_PLATFORM=offscreen python tests/test_control_m1.py
```

开关关着时不监听，离线脑（`brain_tick` / 点她）和以前一样。日志只记 `control say ok` 这种类别，不记台词和口令。

## 任务卡确认流（M2，默认关）

版本号仍是 0.3.10。粉丝包（打包后的 .app）默认还是没有「高级」菜单，除非 `show_control_menu` 为 true。

打开本机通道之后，助手用 `pet_ctl card draft|prepare|receipt|report|withdraw --json-base64 …`。没有 `confirm`。你在任务卡上点「确认 / 改一下 / 不要」。回执写在配置目录的 `receipts.jsonl`（只追加，不进诊断导出）：

```bash
python3 tools/pet_ctl.py card draft --json-base64 <标准 base64 的 UTF-8 JSON>
QT_QPA_PLATFORM=offscreen python tests/test_control_m2.py
```

## 权限

- 运行不需要“屏幕录制”或“辅助功能”权限（空闲检测用的 CGEventSource 不要权限；不读别的窗口）。
- 只有用脚本模拟鼠标拖拽做自动化测试时才需要给终端“辅助功能”权限。
