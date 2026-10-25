# 可选离线语音包

主程序**不带**这 128 句。没有下面这些文件时，桌宠只冒文字气泡，不报错，也不联网。

把预录音频按台词 id 放在这个目录（和 `voice_plan_pet.json` 里的 `id` 一致）：

- `assets/voice/<台词id>.wav`（优先；Windows 的 winsound 只播这种）
- 或 `assets/voice/<台词id>.ogg`（macOS 用系统 `afplay` 播放，Linux 用 paplay / ffplay）

同一句两种都有时，用 wav。

放好之后，右键菜单「声音」里会显示「语音包：已装 N 句」。缺的句子仍然只显示气泡。

源码，或解压后只有 `zhanggui_pet.py` 的源码包：放进本目录。
Windows 安装包：`ZhangguiPet.exe` 旁边的 `_internal\assets\voice\`。
macOS 安装包：`ZhangguiPet.app/Contents/Frameworks/assets/voice/`（和 `Contents/Resources/assets/voice/` 是同一目录）。

这些音频不必提交进主仓库。自己合成时用 `python tools/import_voice.py <合成结果文件夹>`，不要把在线 TTS 接到桌宠的播放路径上。
